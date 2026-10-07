import json
import re
from dataclasses import dataclass
from datetime import datetime, time

import cv2
import numpy as np
from sqlalchemy import select

from app.db.models import Zone
from app.db.session import SessionLocal

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def in_window(now: time, start: str, end: str) -> bool:
    """Whether `now` is within [start, end), where the window may cross midnight."""
    s, e = parse_hhmm(start), parse_hhmm(end)
    if s == e:
        return True
    return s <= now < e if s < e else (now >= s or now < e)


@dataclass(frozen=True)
class ZoneSpec:
    id: int
    name: str
    points: tuple[tuple[float, float], ...]  # normalized 0..1
    severity: str
    schedule_start: str | None
    schedule_end: str | None
    loiter_seconds: int = 0
    repeat_entries: int = 0
    repeat_window_seconds: int = 300

    def is_active(self, when: datetime | None = None) -> bool:
        if not (self.schedule_start and self.schedule_end):
            return True
        return in_window((when or datetime.now()).time(), self.schedule_start, self.schedule_end)

    def contains(self, x: float, y: float, width: int, height: int) -> bool:
        """Is the pixel (x, y) of a width x height frame inside the zone?"""
        polygon = np.array([[px * width, py * height] for px, py in self.points], dtype=np.float32)
        return cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0


def spec_from_row(row: Zone) -> ZoneSpec:
    return ZoneSpec(
        id=row.id,
        name=row.name,
        points=tuple((float(x), float(y)) for x, y in json.loads(row.points)),
        severity=row.severity,
        schedule_start=row.schedule_start,
        schedule_end=row.schedule_end,
        loiter_seconds=row.loiter_seconds or 0,
        repeat_entries=row.repeat_entries or 0,
        repeat_window_seconds=row.repeat_window_seconds or 300,
    )


def load_zone_specs(camera_id: str) -> list[ZoneSpec]:
    with SessionLocal() as db:
        rows = db.scalars(select(Zone).where(Zone.camera_id == camera_id, Zone.enabled.is_(True))).all()
        return [spec_from_row(r) for r in rows]


def draw_zones(frame: np.ndarray, zones: list[ZoneSpec], triggered: set[int] | None = None) -> None:
    """Outline restricted zones on a frame: red when currently enforced (bright
    when someone is inside), gray when outside their schedule."""
    height, width = frame.shape[:2]
    triggered = triggered or set()
    overlay = frame.copy()
    for zone in zones:
        pts = np.array([[int(x * width), int(y * height)] for x, y in zone.points], np.int32)
        active = zone.is_active()
        color = (0, 0, 255) if active else (150, 150, 150)
        cv2.fillPoly(overlay, [pts], color)
        cv2.polylines(frame, [pts], True, color, 3 if zone.id in triggered else 2, cv2.LINE_AA)
        label = f"RESTRICTED: {zone.name}" if active else f"{zone.name} (inactive)"
        cv2.putText(frame, label, (pts[:, 0].min() + 4, pts[:, 1].min() + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
