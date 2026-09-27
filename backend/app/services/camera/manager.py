import logging
import threading
import time

import cv2

from app.services.camera.base import BaseCamera, CameraStatus
from app.services.camera.opencv_camera import OpenCVCamera

logger = logging.getLogger(__name__)

RETRY_INTERVAL_SECONDS = 3.0
CAPTURE_FPS_CAP = 20
JPEG_QUALITY = 80


class CameraWorker:
    """Owns one camera's background capture thread and its latest frame.

    Running capture on a dedicated thread means a slow or hanging camera
    (cap.read() blocks on real hardware/network I/O) never blocks the
    FastAPI event loop, and one camera failing can never take down another
    or the server itself — the thread just keeps retrying in the background.
    """

    def __init__(self, camera: BaseCamera):
        self.camera = camera
        self.status = CameraStatus.CONNECTING
        self._latest_jpeg: bytes | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def camera_id(self) -> str:
        return self.camera.camera_id

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"camera-{self.camera_id}")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.camera.release()

    def get_status(self) -> CameraStatus:
        with self._lock:
            return self.status

    def get_latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._latest_jpeg

    def _set_status(self, status: CameraStatus) -> None:
        with self._lock:
            self.status = status

    def _run(self) -> None:
        min_frame_interval = 1.0 / CAPTURE_FPS_CAP
        while not self._stop_event.is_set():
            if not self.camera.is_opened():
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
                with self._lock:
                    self._latest_jpeg = None
                self._stop_event.wait(RETRY_INTERVAL_SECONDS)
                continue

            self._set_status(CameraStatus.ONLINE)
            encode_ok, buffer = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
            )
            if encode_ok:
                with self._lock:
                    self._latest_jpeg = buffer.tobytes()

            elapsed = time.monotonic() - loop_start
            self._stop_event.wait(max(0.0, min_frame_interval - elapsed))

        self.camera.release()


class CameraManager:
    """Registry of all configured cameras, keyed by camera_id.

    A dict of workers is the whole "multi-camera" story: adding a second
    camera later is just adding a second CameraConfig entry, which produces
    a second independent CameraWorker/thread.
    """

    def __init__(self):
        self._workers: dict[str, CameraWorker] = {}

    def register(self, camera: BaseCamera) -> None:
        self._workers[camera.camera_id] = CameraWorker(camera)

    def start_all(self) -> None:
        for worker in self._workers.values():
            worker.start()

    def stop_all(self) -> None:
        for worker in self._workers.values():
            worker.stop()

    def get(self, camera_id: str) -> CameraWorker | None:
        return self._workers.get(camera_id)

    def list_status(self) -> list[dict]:
        return [
            {
                "id": worker.camera_id,
                "name": worker.camera.name,
                "status": worker.get_status().value,
            }
            for worker in self._workers.values()
        ]


camera_manager = CameraManager()


def warmup_camera_permissions(camera_configs: list) -> None:
    """Open+release local webcam sources once, synchronously, on the caller's thread.

    macOS (AVFoundation) only shows the "App would like to access the
    Camera" permission dialog when the capture device is opened from the
    process's *main* thread. Our real capture loop runs on a background
    thread per camera (see CameraWorker), so without this warmup the very
    first open would fail permanently — the OS never gets a chance to ask,
    and every subsequent attempt on the background thread just errors out.
    This must be called from the main thread before `camera_manager.start_all()`.
    RTSP/IP sources (str) don't need OS camera permission, so they're skipped.
    """
    for cfg in camera_configs:
        if isinstance(cfg.source, int):
            cap = cv2.VideoCapture(cfg.source)
            cap.read()
            cap.release()


def init_cameras_from_settings(camera_configs: list) -> None:
    for cfg in camera_configs:
        camera_manager.register(OpenCVCamera(camera_id=cfg.id, name=cfg.name, source=cfg.source))
