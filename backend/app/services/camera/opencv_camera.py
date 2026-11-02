import logging

import cv2
import numpy as np

from app.services.camera.base import BaseCamera

logger = logging.getLogger(__name__)

NETWORK_TIMEOUT_MS = 5000


class OpenCVCamera(BaseCamera):
    """Camera backed by cv2.VideoCapture.

    One class covers every source type: an int opens a local webcam, a URL
    string opens an RTSP/HTTP stream, and a path opens a video file.

    - `network=True` sets open/read timeouts so an unreachable IP camera
      fails in ~5s instead of hanging its worker thread for a minute.
    - `loop=True` rewinds at end-of-file, so a video file behaves like a
      camera that never goes offline (used to test several sources with one
      physical webcam).
    - `size` / `fps` are *requests* to a local webcam (drivers may pick the
      nearest mode they support). The mode actually obtained is logged.
    """

    def __init__(
        self,
        camera_id: str,
        name: str,
        source: int | str,
        *,
        network: bool = False,
        loop: bool = False,
        size: tuple[int, int] | None = None,
        fps: int | None = None,
    ):
        super().__init__(camera_id, name, source)
        self._network = network
        self._loop = loop
        self._size = size
        self._fps = fps
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> bool:
        self.release()
        if self._network:
            cap = cv2.VideoCapture(
                self.source,
                cv2.CAP_FFMPEG,
                [
                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
                    NETWORK_TIMEOUT_MS,
                    cv2.CAP_PROP_READ_TIMEOUT_MSEC,
                    NETWORK_TIMEOUT_MS,
                ],
            )
        else:
            cap = cv2.VideoCapture(self.source)
            if cap.isOpened() and isinstance(self.source, int):
                if self._size:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._size[0])
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._size[1])
                if self._fps:
                    cap.set(cv2.CAP_PROP_FPS, self._fps)
        if not cap.isOpened():
            cap.release()
            self._cap = None
            return False
        self._cap = cap
        if self._network or isinstance(self.source, int):
            logger.info(
                "Camera %s delivers %dx%d at %.0f fps",
                self.camera_id,
                cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                cap.get(cv2.CAP_PROP_FPS),
            )
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is None:
            return False, None
        try:
            ok, frame = self._cap.read()
            if not ok and self._loop:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
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
