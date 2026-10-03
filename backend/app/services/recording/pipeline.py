import logging
import threading
import time
from datetime import datetime, timezone

import cv2
import numpy as np

from app.core.config import settings
from app.db.models import Event, PersonDetection
from app.db.session import SessionLocal
from app.services.activity.monitor import ActivityMonitor
from app.services.activity.zones import ZoneSpec, draw_zones
from app.services.detection.detector import Detection, PersonDetector
from app.services.faces.service import FaceResult, FaceService
from app.services.faces.tracker import FaceEventTracker, draw_faces
from app.services.motion.detector import MotionDetector
from app.services.night.lighting import LightingAnalyzer, LowLightEnhancer
from app.services.recording.event_types import upgrade_event_type
from app.services.recording.paths import build_recording_path, resolve_recording_path
from app.services.recording.writer import RecordingWriter

logger = logging.getLogger(__name__)

PERSON_BOX_COLOR = (230, 170, 40)  # BGR; kept distinct from the green/red/orange face boxes


class MotionEventPipeline:
    """Per-camera: feed it frames, it detects motion, runs YOLO, and manages recordings.

    Runs entirely inside the camera's own capture thread (see
    CameraWorker._run) — there is no separate recording or detection thread.
    That thread is already a background thread relative to FastAPI's event
    loop/HTTP handling, so the live stream (served from a lock-protected
    "latest frame" the capture thread updates independently) is never
    blocked by motion detection, YOLO inference, or video encoding here; at
    most, heavy work adds a little latency to this camera's own capture
    loop, never to the HTTP server or other cameras.

    YOLO only ever runs while a motion-triggered recording is already
    active, and even then only every `detection.run_every_n_frames` frames
    — this is the main cost control (see core/config.py). This matches the
    requested flow: Motion decides "something is happening", YOLO decides
    "is it a person".
    """

    def __init__(
        self,
        camera_id: str,
        person_detector: PersonDetector | None,
        face_service: FaceService | None = None,
    ):
        self.camera_id = camera_id
        cfg = settings.motion
        self._detector = MotionDetector(
            sensitivity=cfg.sensitivity,
            min_area=cfg.min_area,
            warmup_frames=cfg.warmup_frames,
            lighting_jump_threshold=cfg.lighting_jump_threshold,
        )
        self._writer: RecordingWriter | None = None
        self._event_id: int | None = None
        self._recording_started_at: float = 0.0
        self._last_motion_at: float = 0.0
        self._last_event_ended_at: float | None = None

        # Shared across cameras (see PersonDetector); None = YOLO unavailable.
        self._person_detector = person_detector

        # Shared across cameras; None = face recognition unavailable/disabled.
        self._face_service = face_service
        self._face_tracker = FaceEventTracker(camera_id, settings.face)

        # Night handling (see services/night): lighting is measured every frame.
        self._lighting = LightingAnalyzer(settings.night)
        self._enhancer = LowLightEnhancer(settings.night)
        self._night = False

        # Restricted zones + suspicious-activity rules (see services/activity).
        self._activity = ActivityMonitor(camera_id, settings.activity)
        self._zones: list[ZoneSpec] = []
        self._occupied_zones: set[int] = set()
        self._continue_next = False  # a person is still here when a clip hit its length cap
        self._error_logged: dict[str, float] = {}

        self._frames_since_detection = 0
        self._person_present = False
        self._live_detections: list[Detection] = []
        self._live_faces: list[FaceResult] = []
        self._live_lock = threading.Lock()

    def process(self, frame: np.ndarray) -> np.ndarray:
        """Feed one frame. Returns the frame to show live: the same array,
        or an annotated copy while people are in view / zones are drawn. The
        raw frame itself is never modified (recordings and face registration
        use it as is)."""
        night_cfg = settings.night
        lighting = self._lighting.update(frame)
        if lighting.night != self._night:
            self._night = lighting.night
            self._detector.notify_lighting_change()

        motion = self._detector.process(frame, denoise=self._night and night_cfg.motion_denoise)
        now = time.monotonic()

        if self._writer is not None:
            self._writer.write(frame)  # archive the raw, unannotated frame
            if motion:
                self._last_motion_at = now

            self._run_person_detection(frame)

            recording_age = now - self._recording_started_at
            idle_time = now - self._last_motion_at
            cfg = settings.motion
            if idle_time >= cfg.post_motion_seconds or recording_age >= cfg.max_recording_seconds:
                # A clip that merely hit its length cap while someone is still
                # there continues straight into the next one (no cooldown gap),
                # so a long visit is covered end to end.
                still_active = idle_time < cfg.post_motion_seconds
                self._finalize(status="completed", continuing=still_active and self._person_present)
            return self._render(frame)

        if self._continue_next or motion:
            cooling = (
                self._last_event_ended_at is not None
                and not self._continue_next
                and now - self._last_event_ended_at < settings.motion.cooldown_seconds
            )
            if not cooling:
                self._continue_next = False
                self._start(frame)
        return self._render(frame)

    def set_zones(self, zones: list[ZoneSpec]) -> None:
        self._zones = zones
        self._activity.set_zones(zones)

    def get_lighting(self) -> dict:
        state = self._lighting.state.as_dict()
        cfg = settings.night
        state["enhanced_detection"] = state["night"] and cfg.enhance_for_detection
        state["enhanced_view"] = state["night"] and cfg.enhance_live_view
        return state

    def _log_rate_limited(self, key: str, message: str, seconds: float = 60.0) -> None:
        """Log a repeating failure with its traceback at most once per `seconds`."""
        now = time.monotonic()
        if now - self._error_logged.get(key, float("-inf")) >= seconds:
            self._error_logged[key] = now
            logger.exception("Camera %s: %s (further errors hidden for %ds)", self.camera_id, message, seconds)

    @property
    def is_recording(self) -> bool:
        return self._writer is not None

    def get_live_detections(self) -> list[Detection]:
        """Current in-frame people, for the dashboard's live indicator."""
        with self._live_lock:
            return list(self._live_detections)

    def get_live_faces(self) -> list[FaceResult]:
        """Faces currently in view and how each was classified."""
        with self._live_lock:
            return list(self._live_faces)

    def _run_person_detection(self, frame: np.ndarray) -> None:
        """Run YOLO (throttled) and, when people are found, face recognition
        and the activity rules."""
        if self._person_detector is None:
            return
        self._frames_since_detection += 1
        if self._frames_since_detection >= settings.detection.run_every_n_frames:
            self._frames_since_detection = 0
            self._detect_people(frame)

    def _detect_people(self, frame: np.ndarray) -> None:
        night_cfg = settings.night
        night = self._night
        try:
            detect_frame = frame
            confidence = night_cfg.person_confidence if night else None
            detections = self._person_detector.detect(frame, confidence=confidence)
            if night and night_cfg.enhance_for_detection:
                # Enhancement helps in very dark scenes but can hurt in moderate
                # low light, so at night both versions are tried and the one
                # that finds more people wins (measured: never worse than
                # either alone). The boxes apply to the raw frame just the
                # same; the raw frame is what gets recorded.
                enhanced = self._enhancer.apply(frame)
                enhanced_detections = self._person_detector.detect(enhanced, confidence=confidence)
                if len(enhanced_detections) > len(detections):
                    detections, detect_frame = enhanced_detections, enhanced
        except Exception:
            logger.exception("Camera %s: person detection failed on this frame, skipping", self.camera_id)
            return

        faces = self._recognize_faces(detect_frame, detections, raw_frame=frame) if detections else []
        with self._live_lock:
            self._live_detections = detections
            self._live_faces = faces

        if detections:
            now = time.monotonic()
            self._last_motion_at = now  # someone standing still still counts as activity: keep recording
            best = max(detections, key=lambda d: d.confidence)
            if not self._person_present:
                self._record_new_person(best.confidence, best.bbox)
            else:
                self._bump_event_confidence(best.confidence)
            self._person_present = True
            self._track_faces(faces, frame, night)
            self._run_activity_rules(detections, frame)
        else:
            self._person_present = False
            self._occupied_zones = set()

    def _run_activity_rules(self, detections: list[Detection], frame: np.ndarray) -> None:
        try:
            self._occupied_zones = self._activity.process(detections, frame, self._event_id)
        except Exception:
            self._log_rate_limited("activity", "activity rules failed")

    def _recognize_faces(self, frame: np.ndarray, detections: list[Detection], raw_frame: np.ndarray) -> list[FaceResult]:
        """Face recognition on the people YOLO found. Any failure here is
        contained: the camera, recording and person detection carry on."""
        if self._face_service is None:
            return []
        try:
            results = self._face_service.analyze(frame, regions=[d.bbox for d in detections], brightness_frame=raw_frame)
            return [r for r in results if isinstance(r, FaceResult)]
        except Exception:
            # If recognition is broken it fails on every cycle; log sparingly.
            self._log_rate_limited("faces", "face recognition failed")
            return []

    def _track_faces(self, faces: list[FaceResult], frame: np.ndarray, night: bool = False) -> None:
        if not faces or self._face_service is None:
            return
        try:
            self._face_tracker.handle(faces, frame, self._event_id, self._face_service.people_count, night)
        except Exception:
            logger.exception("Camera %s: could not record face results", self.camera_id)

    def _render(self, frame: np.ndarray) -> np.ndarray:
        """The frame to show live. Overlays (restricted zones, people, faces)
        are drawn on a copy from the latest results every frame, so they stay
        steady between the few frames that actually run the models."""
        with self._live_lock:
            detections, faces = list(self._live_detections), list(self._live_faces)
        show_people = self._person_present and bool(detections or faces)
        zones = self._zones
        enhance_view = self._night and settings.night.enhance_live_view
        if not (show_people or zones or enhance_view):
            return frame
        try:
            display = self._enhancer.apply(frame) if enhance_view else frame.copy()
            if zones:
                draw_zones(display, zones, self._occupied_zones)
            if show_people:
                self._draw_detections(display, detections)
                draw_faces(display, faces)
            return display
        except Exception:
            # Overlays are cosmetic: never let a drawing problem stop the feed.
            self._log_rate_limited("render", "could not draw overlays")
            return frame

    @staticmethod
    def _draw_detections(frame: np.ndarray, detections: list[Detection]) -> None:
        for d in detections:
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), PERSON_BOX_COLOR, 1)
            cv2.putText(
                frame,
                f"person {d.confidence:.0%}",
                (x1, max(y1 - 8, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                PERSON_BOX_COLOR,
                1,
                cv2.LINE_AA,
            )

    def _record_new_person(self, confidence: float, bbox: tuple[int, int, int, int]) -> None:
        with SessionLocal() as session:
            if self._event_id is not None:
                event = session.get(Event, self._event_id)
                if event is not None:
                    upgrade_event_type(event, "person")
                    if event.max_confidence is None or confidence > event.max_confidence:
                        event.max_confidence = confidence
            x1, y1, x2, y2 = bbox
            session.add(
                PersonDetection(
                    event_id=self._event_id,
                    camera_id=self.camera_id,
                    confidence=confidence,
                    bbox_x1=x1,
                    bbox_y1=y1,
                    bbox_x2=x2,
                    bbox_y2=y2,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            session.commit()
        logger.info("Camera %s: person detected (confidence %.2f)", self.camera_id, confidence)

    def _bump_event_confidence(self, confidence: float) -> None:
        if self._event_id is None:
            return
        with SessionLocal() as session:
            event = session.get(Event, self._event_id)
            if event is not None and (event.max_confidence is None or confidence > event.max_confidence):
                event.max_confidence = confidence
                session.commit()

    def _start(self, frame: np.ndarray) -> None:
        started_at = datetime.now(timezone.utc)
        relative_path = build_recording_path(self.camera_id, started_at)
        absolute_path = resolve_recording_path(str(relative_path))

        height, width = frame.shape[:2]
        self._writer = RecordingWriter(absolute_path, fps=settings.capture_fps, frame_size=(width, height))

        with SessionLocal() as session:
            event = Event(
                camera_id=self.camera_id,
                event_type="motion",
                timestamp=started_at,
                recording_path=str(relative_path),
                status="recording",
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            self._event_id = event.id

        now = time.monotonic()
        self._recording_started_at = now
        self._last_motion_at = now
        self._frames_since_detection = 0
        self._person_present = False
        self._face_tracker.reset_event()
        logger.info("Camera %s: motion detected, recording event %s", self.camera_id, self._event_id)

    def _finalize(self, status: str, continuing: bool = False) -> None:
        if self._writer is None:
            return

        recorded_path = self._writer.path
        self._writer.close()
        self._writer = None

        file_ok = recorded_path.is_file() and recorded_path.stat().st_size > 0
        final_status = status if file_ok else "failed"

        if self._event_id is not None:
            with SessionLocal() as session:
                event = session.get(Event, self._event_id)
                if event is not None:
                    event.ended_at = datetime.now(timezone.utc)
                    event.status = final_status
                    session.commit()
            logger.info("Camera %s: event %s finalized as %s", self.camera_id, self._event_id, final_status)

        self._event_id = None
        self._last_event_ended_at = time.monotonic()
        self._continue_next = continuing
        self._person_present = False
        self._occupied_zones = set()
        with self._live_lock:
            self._live_detections = []
            self._live_faces = []

    def close(self) -> None:
        """Called when the camera worker stops (app shutdown or camera loss)."""
        if self._writer is not None:
            self._finalize(status="interrupted")
