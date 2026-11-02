from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.db.models import Camera, CameraRules, Zone
from app.db.session import SessionLocal
from app.security.deps import current_user, require_admin
from app.services.activity.rules import load_rules
from app.services.activity.zones import HHMM
from app.services.camera.manager import camera_manager

router = APIRouter(tags=["rules"], dependencies=[Depends(current_user)])


class RulesBody(BaseModel):
    quiet_start: str | None = None
    quiet_end: str | None = None
    fall_detection: bool = False
    crowd_threshold: int = Field(0, ge=0, le=50)  # 0 = off
    crowd_seconds: int = Field(10, ge=3, le=3600)
    crowd_zone_id: int | None = None

    @field_validator("quiet_start", "quiet_end")
    @classmethod
    def _time(cls, value):
        if value is not None and not HHMM.match(value):
            raise ValueError("time must be HH:MM (24-hour)")
        return value


def _serialize(rules) -> dict:
    return {
        "quiet_start": rules.quiet_start, "quiet_end": rules.quiet_end, "fall_detection": rules.fall_enabled,
        "crowd_threshold": rules.crowd_threshold, "crowd_seconds": rules.crowd_seconds, "crowd_zone_id": rules.crowd_zone_id,
    }


@router.get("/cameras/{camera_id}/rules")
def get_rules(camera_id: str):
    with SessionLocal() as db:
        if db.get(Camera, camera_id) is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
    return _serialize(load_rules(camera_id))


@router.put("/cameras/{camera_id}/rules", dependencies=[Depends(require_admin)])
def set_rules(camera_id: str, body: RulesBody):
    if (body.quiet_start is None) != (body.quiet_end is None):
        raise HTTPException(status_code=422, detail="Set both security-hour times, or neither")
    if body.quiet_start is not None and body.quiet_start == body.quiet_end:
        raise HTTPException(status_code=422, detail="Security hours must start and end at different times")
    if body.crowd_threshold == 1:
        raise HTTPException(status_code=422, detail="A crowd needs at least 2 people (use 0 to turn the rule off)")
    with SessionLocal() as db:
        if db.get(Camera, camera_id) is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
        if body.crowd_zone_id is not None:
            zone = db.get(Zone, body.crowd_zone_id)
            if zone is None or zone.camera_id != camera_id:
                raise HTTPException(status_code=422, detail="The crowd zone must be a zone of this camera")
        row = db.get(CameraRules, camera_id) or CameraRules(camera_id=camera_id)
        row.quiet_start, row.quiet_end, row.fall_detection = body.quiet_start, body.quiet_end, body.fall_detection
        row.crowd_threshold, row.crowd_seconds, row.crowd_zone_id = body.crowd_threshold, body.crowd_seconds, body.crowd_zone_id
        db.add(row)
        db.commit()
    camera_manager.reload_rules(camera_id)
    return _serialize(load_rules(camera_id))
