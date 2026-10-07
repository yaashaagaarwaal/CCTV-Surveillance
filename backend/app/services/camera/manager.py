import logging
import threading
import time

import cv2
import numpy as np

from app.core.config import settings
from app.services.activity.rules import RulesSpec, load_rules
from app.services.activity.zones import ZoneSpec, load_zone_specs
from app.services.alerts import raise_alert, resolve_by_key
from app.services.camera.base import BaseCamera, CameraStatus
from app.services.camera.factory import CameraSpec, build_camera
from app.services.detection.detector import Detection, PersonDetector
from app.services.faces.service import FaceResult, FaceService
from app.services.recording.pipeline import MotionEventPipeline

logger = logging.getLogger(__name__)

RETRY_INTERVAL_SECONDS = 3.0
JPEG_QUALITY = 80


class CameraWorker:
    """Owns one camera's background capture thread and its latest frame.

    Every camera gets its own worker, thread, motion detector and recording
    pipeline, so cameras are fully independent: a slow, hung, unplugged or
    crashing camera only ever affects its own thread — it keeps retrying in
    the background while every other camera and the API carry on.
    """

    def __init__(self, spec: CameraSpec, camera: BaseCamera, pipeline: MotionEventPipeline):
        self.spec = spec
        self.name = spec.name
        self.camera = camera
        self.status = CameraStatus.CONNECTING
        self._pipeline = pipeline
        self._latest_jpeg: bytes | None = None
        self._latest_raw: np.ndarray | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._offline_since: float | None = None
        self._offline_alerted = False

    @property
    def camera_id(self) -> str:
        return self.spec.id

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"camera-{self.camera_id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=8)
        self.camera.release()
        self._pipeline.close()

    def get_status(self) -> CameraStatus:
        with self._lock:
            return self.status

    def get_latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def get_latest_frame(self) -> np.ndarray | None:
        """Latest raw frame (no overlays), e.g. for registering a face."""
        with self._lock:
            return None if self._latest_raw is None else self._latest_raw.copy()

    def get_live_detections(self) -> list[Detection]:
        return self._pipeline.get_live_detections()

    def get_live_faces(self) -> list[FaceResult]:
        return self._pipeline.get_live_faces()

    def get_lighting(self) -> dict:
        return self._pipeline.get_lighting()

    def set_zones(self, zones: list[ZoneSpec]) -> None:
        self._pipeline.set_zones(zones)

    def set_rules(self, rules: RulesSpec) -> None:
        self._pipeline.set_rules(rules)

    @property
    def is_recording(self) -> bool:
        return self._pipeline.is_recording

    def _set_status(self, status: CameraStatus) -> None:
        with self._lock:
            previous, self.status = self.status, status
        if status == CameraStatus.OFFLINE and self._offline_since is None:
            self._offline_since = time.monotonic()
        elif status == CameraStatus.ONLINE and previous != CameraStatus.ONLINE:
            self._offline_since = None
            self._offline_alerted = False
            self._safely(resolve_by_key, self._offline_key, "system")  # back online: close any open outage alert

    @property
    def _offline_key(self) -> str:
        return f"camera_offline:{self.camera_id}"

    def _safely(self, func, *args, **kwargs) -> None:
        """Alert bookkeeping must never be able to break capture."""
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception("Camera %s: alert bookkeeping failed", self.camera_id)

    def _check_offline_alert(self) -> None:
        """Raise one alert once the camera has been offline longer than the
        grace period (so a brief blip doesn't alert). It is resolved
        automatically when the camera comes back."""
        if self._offline_since is None or self._offline_alerted:
            return
        outage = time.monotonic() - self._offline_since
        if outage >= settings.alerts.camera_offline_grace_seconds:
            self._offline_alerted = True
            self._safely(
                raise_alert,
                alert_type="camera_offline",
                severity="medium",
                camera_id=self.camera_id,
                message="Camera is offline",
                details={"offline_seconds_at_alert": int(outage)},
                dedupe_key=self._offline_key,
            )

    def _run(self) -> None:
        min_frame_interval = 1.0 / settings.capture_fps
        while not self._stop_event.is_set():
            self._check_offline_alert()
            if not self.camera.is_opened():
                # Only the first attempt shows "connecting"; after a failure the
                # camera stays "offline" while it quietly retries, instead of
                # flickering between the two on every retry.
                if self.get_status() != CameraStatus.OFFLINE:
                    self._set_status(CameraStatus.CONNECTING)
                try:
                    opened = self.camera.open()
                except Exception:
                    logger.exception("Unexpected error opening camera %s", self.camera_id)
                    opened = False
                if not opened:
                    self._set_status(CameraStatus.OFFLINE)
                    self._stop_event.wait(RETRY_INTERVAL_SECONDS)
                    continue
                logger.info("Camera %s opened", self.camera_id)

            loop_start = time.monotonic()
            try:
                ok, frame = self.camera.read()
            except Exception:
                logger.exception("Unexpected error reading camera %s", self.camera_id)
                ok, frame = False, None

            if not ok or frame is None:
                logger.warning("Camera %s read failed, marking offline and retrying", self.camera_id)
                self._set_status(CameraStatus.OFFLINE)
                self.camera.release()
                self._pipeline.close()  # finalize any in-progress recording as "interrupted"
                with self._lock:
                    self._latest_jpeg = None
                    self._latest_raw = None
                self._stop_event.wait(RETRY_INTERVAL_SECONDS)
                continue

            self._set_status(CameraStatus.ONLINE)

            display = frame
            try:
                display = self._pipeline.process(frame)
            except Exception:
                # A bug in motion detection/recording must never take down
                # capture or the live stream for this (or any other) camera.
                logger.exception("Motion/recording pipeline error for camera %s", self.camera_id)

            encode_ok, buffer = cv2.imencode(".jpg", display, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            with self._lock:
                self._latest_raw = frame
                if encode_ok:
                    self._latest_jpeg = buffer.tobytes()

            elapsed = time.monotonic() - loop_start
            self._stop_event.wait(max(0.0, min_frame_interval - elapsed))

        self.camera.release()


class CameraManager:
    """Registry of running cameras, keyed by camera_id, changeable at runtime.

    Cameras are added/removed/restarted while the app is running (from the
    Cameras page), so all access to the worker dict goes through a lock.
    Disabled cameras simply have no worker.
    """

    def __init__(self):
        self._workers: dict[str, CameraWorker] = {}
        self._lock = threading.RLock()
        self._person_detector: PersonDetector | None = None
        self._face_service: FaceService | None = None

    def set_person_detector(self, detector: PersonDetector | None) -> None:
        self._person_detector = detector

    def set_face_service(self, service: FaceService | None) -> None:
        self._face_service = service

    def start_camera(self, spec: CameraSpec) -> None:
        """Start (or restart) a camera. Never raises for a bad/unreachable
        source — such a camera just reports offline and keeps retrying."""
        self.stop_camera(spec.id)  # replace any running instance; alerts are left alone
        try:
            camera = build_camera(spec)
        except Exception:
            logger.exception("Camera %s could not be created, not started", spec.id)
            return
        pipeline = MotionEventPipeline(spec.id, self._person_detector, self._face_service)
        try:
            pipeline.set_zones(load_zone_specs(spec.id))
        except Exception:
            logger.exception("Camera %s: could not load restricted zones", spec.id)
        try:
            pipeline.set_rules(load_rules(spec.id))
        except Exception:
            logger.exception("Camera %s: could not load security rules", spec.id)
        worker = CameraWorker(spec, camera, pipeline)
        with self._lock:
            self._workers[spec.id] = worker
        worker.start()
        logger.info("Started camera %s (%s: %s)", spec.id, spec.type, spec.name)

    def stop_camera(self, camera_id: str, *, resolve_alerts: bool = False) -> None:
        """Stop a camera. `resolve_alerts` is for deliberate stops (disabled,
        edited, deleted) — an outage alert no longer applies. An app shutdown
        leaves alerts alone so a real outage survives a restart."""
        with self._lock:
            worker = self._workers.pop(camera_id, None)
        if worker is not None:
            worker.stop()
            logger.info("Stopped camera %s", camera_id)
        if resolve_alerts:
            try:
                resolve_by_key(f"camera_offline:{camera_id}", "system")
            except Exception:
                logger.exception("Could not resolve alerts for camera %s", camera_id)

    def reload_zones(self, camera_id: str) -> None:
        worker = self.get(camera_id)
        if worker is not None:
            worker.set_zones(load_zone_specs(camera_id))

    def reload_rules(self, camera_id: str) -> None:
        worker = self.get(camera_id)
        if worker is not None:
            worker.set_rules(load_rules(camera_id))

    def stop_all(self) -> None:
        with self._lock:
            ids = list(self._workers)
        for camera_id in ids:
            self.stop_camera(camera_id)

    def rename(self, camera_id: str, name: str) -> None:
        worker = self.get(camera_id)
        if worker is not None:
            worker.name = name

    def get(self, camera_id: str) -> CameraWorker | None:
        with self._lock:
            return self._workers.get(camera_id)

    def runtime_info(self, camera_id: str) -> dict:
        """Live state for one camera; a camera with no worker is not running."""
        worker = self.get(camera_id)
        if worker is None:
            return {**EMPTY_RUNTIME, "status": "offline"}
        detections = worker.get_live_detections()
        faces = worker.get_live_faces()
        return {
            "status": worker.get_status().value,
            "recording": worker.is_recording,
            "people_detected": len(detections),
            "detections": [{"confidence": d.confidence, "bbox": d.bbox} for d in detections],
            "faces": [
                {"label": f.label, "name": f.name, "similarity": f.similarity, "reason": f.reason} for f in faces
            ],
            "lighting": worker.get_lighting() if worker.get_status() == CameraStatus.ONLINE else None,
        }


EMPTY_RUNTIME = {"recording": False, "people_detected": 0, "detections": [], "faces": [], "lighting": None}

camera_manager = CameraManager()


def warmup_camera_permissions(specs: list[CameraSpec]) -> None:
    """Open+release local webcams once, synchronously, on the caller's thread.

    macOS (AVFoundation) only shows the "App would like to access the
    Camera" permission dialog when the capture device is opened from the
    process's *main* thread. Capture runs on background threads, so without
    this warmup the very first open would fail permanently. Call it from
    the main thread (startup, or an `async def` request handler — uvicorn's
    event loop runs on the main thread) before starting a webcam camera.
    Non-webcam sources don't need OS camera permission and are skipped.
    """
    for spec in specs:
        if spec.type == "webcam":
            cap = cv2.VideoCapture(int(spec.source))
            cap.read()
            cap.release()
