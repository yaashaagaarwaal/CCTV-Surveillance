import logging
import re
from uuid import uuid4

from sqlalchemy import func, select

from app.core.config import settings
from app.db.models import Camera, Event
from app.db.session import SessionLocal
from app.services.camera.factory import CameraSpec, mask_source
from app.services.camera.manager import EMPTY_RUNTIME, camera_manager

logger = logging.getLogger(__name__)


def spec_from_row(row: Camera) -> CameraSpec:
    return CameraSpec(id=row.id, name=row.name, type=row.type, source=row.source)


def new_camera_id(name: str) -> str:
    """Readable, filesystem-safe id. The random suffix means a deleted
    camera's id is never reused, so old recordings can't be mixed up with a
    new camera of the same name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "camera"
    return f"{slug}-{uuid4().hex[:4]}"


def seed_default_camera() -> None:
    """Fresh install only: no cameras and no history -> add the local webcam."""
    if not settings.seed_default_camera:
        return
    with SessionLocal() as session:
        has_cameras = session.scalar(select(func.count()).select_from(Camera))
        has_events = session.scalar(select(func.count()).select_from(Event))
        if has_cameras or has_events:
            return
        session.add(Camera(id="cam1", name="Local Webcam", type="webcam", source="0", enabled=True))
        session.commit()
        logger.info("First run: added default 'Local Webcam' camera")


def load_enabled_specs() -> list[CameraSpec]:
    with SessionLocal() as session:
        rows = session.scalars(select(Camera).where(Camera.enabled.is_(True)).order_by(Camera.created_at)).all()
        return [spec_from_row(r) for r in rows]


def serialize_camera(row: Camera) -> dict:
    runtime = camera_manager.runtime_info(row.id) if row.enabled else {**EMPTY_RUNTIME, "status": "disabled"}
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "source": row.source,
        "source_display": mask_source(row.type, row.source),
        "enabled": row.enabled,
        "created_at": row.created_at.isoformat() + "Z",
        **runtime,
    }
