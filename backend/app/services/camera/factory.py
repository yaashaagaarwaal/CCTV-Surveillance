from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.core.config import settings
from app.services.camera.base import BaseCamera
from app.services.camera.opencv_camera import OpenCVCamera

CAMERA_TYPES = ("webcam", "rtsp", "http", "file")


class SourceError(ValueError):
    """The camera source is invalid for the given camera type."""


@dataclass(frozen=True)
class CameraSpec:
    """Plain, thread-safe description of a camera (no ORM object leaks into
    worker threads)."""

    id: str
    name: str
    type: str
    source: str


def _resolve_video_file(source: str) -> Path:
    base = settings.video_sources_dir.resolve()
    path = Path(source)
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    if not path.is_relative_to(base):
        raise SourceError(f"Video files must be inside {base}")
    if not path.is_file():
        raise SourceError(f"Video file not found: {path.name}")
    return path


def normalize_source(camera_type: str, source: str) -> str:
    """Validate `source` for `camera_type` and return its canonical form."""
    source = source.strip()
    if camera_type not in CAMERA_TYPES:
        raise SourceError(f"Unknown camera type '{camera_type}'")
    if not source:
        raise SourceError("Source is required")

    if camera_type == "webcam":
        if not source.isdigit():
            raise SourceError("Webcam source must be a device index like 0 or 1")
        return str(int(source))
    if camera_type == "rtsp":
        if not source.lower().startswith(("rtsp://", "rtsps://")):
            raise SourceError("RTSP source must start with rtsp://")
        return source
    if camera_type == "http":
        if not source.lower().startswith(("http://", "https://")):
            raise SourceError("HTTP source must start with http:// or https://")
        return source
    return _resolve_video_file(source).relative_to(settings.video_sources_dir.resolve()).as_posix()


def mask_source(camera_type: str, source: str) -> str:
    """Hide the password in rtsp/http URLs for display."""
    if camera_type not in ("rtsp", "http"):
        return source
    parts = urlsplit(source)
    if parts.password:
        netloc = f"{parts.username}:****@{parts.hostname}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit(parts._replace(netloc=netloc))
    return source


def build_camera(spec: CameraSpec) -> BaseCamera:
    if spec.type == "webcam":
        return OpenCVCamera(spec.id, spec.name, int(spec.source))
    if spec.type == "file":
        path = _resolve_video_file(spec.source)
        return OpenCVCamera(spec.id, spec.name, str(path), loop=True)
    return OpenCVCamera(spec.id, spec.name, spec.source, network=True)
