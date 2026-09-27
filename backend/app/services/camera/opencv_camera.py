import logging

import cv2
import numpy as np

from app.services.camera.base import BaseCamera

logger = logging.getLogger(__name__)


class OpenCVCamera(BaseCamera):
    """Camera backed by cv2.VideoCapture.

    `source=0` opens the Mac's built-in/USB webcam. Passing an RTSP or HTTP
    URL string (e.g. "rtsp://user:pass@192.168.1.50:554/stream1") instead of
    an int works with this exact same class — VideoCapture handles both, so
    no new class is needed to support IP cameras later.
    """

    def __init__(self, camera_id: str, name: str, source: int | str):
        super().__init__(camera_id, name, source)
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self.release()
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            cap.release()
            self._cap = None
            return False
        self._cap = cap
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            return False, None
        try:
            ok, frame = self._cap.read()
        except cv2.error:
            logger.exception("OpenCV error reading camera %s", self.camera_id)
            return False, None
        return ok, frame if ok else None

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
