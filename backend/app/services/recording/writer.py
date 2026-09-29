import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 'avc1' = H.264. This matters: OpenCV's other common fourcc, 'mp4v'
# (MPEG-4 Part 2), writes fine but is NOT playable by Chrome/Safari's
# <video> tag — recordings would save successfully yet never play back in
# the dashboard. 'avc1' was verified on this Mac to produce real H.264
# (confirmed by reading the fourcc back off the written file).
FOURCC = cv2.VideoWriter_fourcc(*"avc1")


class RecordingWriter:
    """Thin wrapper around cv2.VideoWriter for a single event's clip."""

    def __init__(self, path: Path, fps: int, frame_size: tuple[int, int]):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._writer = cv2.VideoWriter(str(path), FOURCC, fps, frame_size)
        if not self._writer.isOpened():
            logger.error("Failed to open VideoWriter for %s", path)

    @property
    def is_open(self) -> bool:
        return self._writer is not None and self._writer.isOpened()

    def write(self, frame: np.ndarray) -> None:
        if self.is_open:
            self._writer.write(frame)

    def close(self) -> None:
        if self._writer is not None:
            self._writer.release()
            self._writer = None
