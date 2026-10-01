import logging
import threading
import time
from datetime import datetime, timezone

import cv2
import numpy as np

from app.core.config import settings
from app.db.models import Event, PersonDetection
from app.db.session import SessionLocal
from app.services.detection.detector import Detection, PersonDetector
from app.services.motion.detector import MotionDetector
from app.services.recording.paths import build_recording_path, resolve_recording_path
from app.services.recording.writer import RecordingWriter

logger = logging.getLogger(__name__)

BOX_COLOR = (0, 200, 0)  # BGR


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

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        cfg = settings.motion
        self._detector = MotionDetector(
            sensitivity=cfg.sensitivity,
            min_area=cfg.min_area,
            warmup_frames=cfg.warmup_frames,
        )
        self._writer: RecordingWriter | None = None
        self._event_id: int | None = None
        self._recording_started_at: float = 0.0
        self._last_motion_at: float = 0.0
        self._last_event_ended_at: float | None = None

        self._person_detector: PersonDetector | None = None
        if settings.detection.enabled:
            try:
                self._person_detector = PersonDetector(settings.detection)
            except Exception:
                logger.exception(
                    "Camera %s: failed to load YOLO model, person detection disabled "
                    "(motion detection & recording are unaffected)",
                    camera_id,
                )
                self._person_detector = None

        self._frames_since_detection = 0
        self._person_present = False
        self._live_detections: list[Detection] = []
        self._live_lock = threading.Lock()

    def process(self, frame: np.ndarray) -> None:
        motion = self._detector.process(frame)
        now = time.monotonic()

        if self._writer is not None:
            self._writer.write(frame)  # archive the raw, unannotated frame
            if motion:
                self._last_motion_at = now

            self._run_person_detection(frame)  # may draw boxes onto `frame` in place

            recording_age = now - self._recording_started_at
            idle_time = now - self._last_motion_at
            cfg = settings.motion
            if idle_time >= cfg.post_motion_seconds or recording_age >= cfg.max_recording_seconds:
                self._finalize(status="completed")
            return

        if not motion:
            return

        if self._last_event_ended_at is not None:
            if now - self._last_event_ended_at < settings.motion.cooldown_seconds:
                return  # still cooling down since the last event ended

        self._start(frame)

    def get_live_detections(self) -> list[Detection]:
        """Current in-frame people, for the dashboard's live indicator."""
        with self._live_lock:
            return list(self._live_detections)

    def _run_person_detection(self, frame: np.ndarray) -> None:
        if self._person_detector is None:
            return

        # Drawing the last-known boxes is cheap and happens every frame, so
        # the live view shows a steady overlay instead of a box that only
        # flickers on during the one frame in N that actually ran YOLO.
        # Only the (expensive) inference itself is throttled below.
        if self._person_present:
            with self._live_lock:
                detections_to_draw = list(self._live_detections)
            self._draw_detections(frame, detections_to_draw)

        self._frames_since_detection += 1
        if self._frames_since_detection < settings.detection.run_every_n_frames:
            return
        self._frames_since_detection = 0

        try:
            detections = self._person_detector.detect(frame)
        except Exception:
            logger.exception("Camera %s: person detection failed on this frame, skipping", self.camera_id)
            return

        with self._live_lock:
            self._live_detections = detections
        if not self._person_present:
            self._draw_detections(frame, detections)

        if detections:
            best = max(detections, key=lambda d: d.confidence)
            if not self._person_present:
                self._record_new_person(best.confidence, best.bbox)
            else:
                self._bump_event_confidence(best.confidence)
            self._person_present = True
        else:
            self._person_present = False

    @staticmethod
    def _draw_detections(frame: np.ndarray, detections: list[Detection]) -> None:
        for d in detections:
            x1, y1, x2, y2 = d.bbox
            cv2.rectangle(frame, (x1, y1), (x2, y2), BOX_COLOR, 2)
            label = f"person {d.confidence:.0%}"
            label_y = max(y1 - 8, 12)
            cv2.putText(
                frame, label, (x1, label_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, BOX_COLOR, 1, cv2.LINE_AA
            )

    def _record_new_person(self, confidence: float, bbox: tuple[int, int, int, int]) -> None:
        with SessionLocal() as session:
            if self._event_id is not None:
                event = session.get(Event, self._event_id)
                if event is not None:
                    event.event_type = "person"
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
        logger.info("Camera %s: motion detected, recording event %s", self.camera_id, self._event_id)

    def _finalize(self, status: str) -> None:
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
        self._person_present = False
        with self._live_lock:
            self._live_detections = []

    def close(self) -> None:
        """Called when the camera worker stops (app shutdown or camera loss)."""
        if self._writer is not None:
            self._finalize(status="interrupted")
