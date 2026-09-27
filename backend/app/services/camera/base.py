from abc import ABC, abstractmethod
from enum import Enum

import numpy as np


class CameraStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"


class BaseCamera(ABC):
    """Interface every camera backend must implement.

    A `source` is intentionally untyped (`int | str`) so the same interface
    covers a local webcam index (0, 1, ...) today and an RTSP/HTTP IP-camera
    URL later, with no change to callers.
    """

    def __init__(self, camera_id: str, name: str, source: int | str):
        self.camera_id = camera_id
        self.name = name
        self.source = source

    @abstractmethod
    def open(self) -> bool:
        """Attempt to open the camera. Returns True on success."""

    @abstractmethod
    def read(self) -> tuple[bool, np.ndarray | None]:
        """Grab one frame. Returns (success, frame)."""

    @abstractmethod
    def is_opened(self) -> bool:
        """Whether the underlying capture device is currently open."""

    @abstractmethod
    def release(self) -> None:
        """Release any underlying OS/hardware resources."""
