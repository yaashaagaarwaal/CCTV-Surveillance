from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import settings


def build_recording_path(camera_id: str, started_at: datetime) -> Path:
    """Relative path (under settings.storage_dir) for a new recording.

    Organized as recordings/<camera_id>/<date>/<camera_id>_<timestamp>_<uid>.mp4
    so files stay browsable/manageable on disk, and the timestamp + short
    uuid suffix keep filenames unique even for two events starting the same
    second.
    """
    date_dir = started_at.strftime("%Y-%m-%d")
    filename = f"{camera_id}_{started_at.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.mp4"
    return Path(settings.recordings_dir_name) / camera_id / date_dir / filename


def resolve_recording_path(relative_path: str) -> Path:
    return settings.storage_dir / relative_path
