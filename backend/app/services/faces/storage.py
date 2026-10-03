import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np

from app.core.config import settings


def private_dir(path: Path) -> Path:
    """Create a directory only the current user can read (face data is biometric)."""
    path.mkdir(parents=True, exist_ok=True)
    # Lock down every folder between storage/ and here (mkdir leaves the
    # intermediate ones at the default, world-readable mode).
    root = settings.storage_dir
    current = path
    while current != root and root in current.parents:
        os.chmod(current, 0o700)
        current = current.parent
    return path


def write_private_jpeg(path: Path, image: np.ndarray, quality: int = 88) -> None:
    private_dir(path.parent)
    if not cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, quality]):
        raise OSError(f"Could not write image {path}")
    os.chmod(path, 0o600)


def new_face_sample_path(person_id: int) -> Path:
    """Relative path (under storage_dir) for an enrolled face thumbnail."""
    return Path(settings.faces_dir_name) / str(person_id) / f"{uuid4().hex}.jpg"


def new_snapshot_path(camera_id: str, when: datetime, prefix: str = "unknown") -> Path:
    """Relative path (under storage_dir) for an alert snapshot."""
    name = f"{prefix}_{when.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.jpg"
    return Path(settings.snapshots_dir_name) / camera_id / when.strftime("%Y-%m-%d") / name


def resolve(relative: str) -> Path:
    return settings.storage_dir / relative
