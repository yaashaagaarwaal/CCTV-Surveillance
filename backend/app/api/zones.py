import json

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.db.models import Camera, Zone
from app.db.session import SessionLocal
from app.security.deps import current_user, require_admin
from app.services.activity.zones import HHMM
from app.services.alerts import SEVERITIES, iso_utc
from app.services.camera.manager import camera_manager

router = APIRouter(tags=["zones"], dependencies=[Depends(current_user)])


class ZoneBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    points: list[list[float]] = Field(min_length=3, max_length=50)
    enabled: bool = True
    schedule_start: str | None = None
    schedule_end: str | None = None
    severity: str = "high"

    @field_validator("points")
    @classmethod
    def _points_in_frame(cls, points):
        for point in points:
            if len(point) != 2 or not all(0.0 <= v <= 1.0 for v in point):
                raise ValueError("each point must be [x, y] with both values between 0 and 1")
        # Shoelace formula: reject zero-area shapes (all points in a line).
        area = abs(sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1] for i in range(len(points)))) / 2
        if area < 0.0005:
            raise ValueError("the zone is too small or flat")
        return points

    @field_validator("severity")
    @classmethod
    def _severity(cls, value):
        if value not in SEVERITIES:
            raise ValueError(f"severity must be one of {', '.join(SEVERITIES)}")
        return value

    @field_validator("schedule_start", "schedule_end")
    @classmethod
    def _time(cls, value):
        if value is not None and not HHMM.match(value):
            raise ValueError("time must be HH:MM (24-hour)")
        return value


def _serialize(zone: Zone) -> dict:
    return {
        "id": zone.id,
        "camera_id": zone.camera_id,
        "name": zone.name,
        "points": json.loads(zone.points),
        "enabled": zone.enabled,
        "schedule_start": zone.schedule_start,
        "schedule_end": zone.schedule_end,
        "severity": zone.severity,
        "created_at": iso_utc(zone.created_at),
    }


def _check_schedule(body: ZoneBody) -> None:
    if (body.schedule_start is None) != (body.schedule_end is None):
        raise HTTPException(status_code=422, detail="Set both schedule times, or neither")


@router.get("/cameras/{camera_id}/zones")
def list_zones(camera_id: str):
    with SessionLocal() as db:
        if db.get(Camera, camera_id) is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
        return [_serialize(z) for z in db.scalars(select(Zone).where(Zone.camera_id == camera_id).order_by(Zone.id))]


@router.post("/cameras/{camera_id}/zones", status_code=201, dependencies=[Depends(require_admin)])
def create_zone(camera_id: str, body: ZoneBody):
    _check_schedule(body)
    with SessionLocal() as db:
        if db.get(Camera, camera_id) is None:
            raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
        zone = Zone(camera_id=camera_id, name=body.name.strip(), points=json.dumps(body.points), enabled=body.enabled,
                    schedule_start=body.schedule_start, schedule_end=body.schedule_end, severity=body.severity)
        db.add(zone)
        db.commit()
        result = _serialize(zone)
    camera_manager.reload_zones(camera_id)
    return result


@router.patch("/zones/{zone_id}", dependencies=[Depends(require_admin)])
def update_zone(zone_id: int, body: ZoneBody):
    _check_schedule(body)
    with SessionLocal() as db:
        zone = db.get(Zone, zone_id)
        if zone is None:
            raise HTTPException(status_code=404, detail="Zone not found")
        zone.name, zone.points, zone.enabled = body.name.strip(), json.dumps(body.points), body.enabled
        zone.schedule_start, zone.schedule_end, zone.severity = body.schedule_start, body.schedule_end, body.severity
        db.commit()
        camera_id, result = zone.camera_id, _serialize(zone)
    camera_manager.reload_zones(camera_id)
    return result


@router.delete("/zones/{zone_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_zone(zone_id: int):
    with SessionLocal() as db:
        zone = db.get(Zone, zone_id)
        if zone is None:
            raise HTTPException(status_code=404, detail="Zone not found")
        camera_id = zone.camera_id
        db.delete(zone)
        db.commit()
    camera_manager.reload_zones(camera_id)
    return Response(status_code=204)
