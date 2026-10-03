import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np

from app.core.config import ActivityConfig
from app.db.models import Event
from app.db.session import SessionLocal
from app.services.activity.zones import ZoneSpec, draw_zones, in_window
from app.services.alerts import raise_alert
from app.services.detection.detector import Detection
from app.services.faces.storage import new_snapshot_path, resolve, write_private_jpeg
from app.services.recording.event_types import upgrade_event_type

logger = logging.getLogger(__name__)

TRACK_TIMEOUT_SECONDS = 4.0


@dataclass
class Track:
    id: int
    centroid: tuple[float, float]
    first_seen: float
    last_seen: float
    loiter_alerted: bool = False

    @property
    def dwell(self) -> float:
        return self.last_seen - self.first_seen


@dataclass
class PersonTracker:
    """Follows people between detection cycles by nearest-centroid matching.
    Deliberately simple: it only has to answer "has someone been continuously
    in view for N seconds?", not tell individuals apart in a crowd."""

    tracks: list[Track] = field(default_factory=list)
    _next_id: int = 1

    def update(self, detections: list[Detection], now: float) -> list[Track]:
        self.tracks = [t for t in self.tracks if now - t.last_seen <= TRACK_TIMEOUT_SECONDS]
        unmatched = list(self.tracks)
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            centroid = ((x1 + x2) / 2, (y1 + y2) / 2)
            reach = 0.75 * max(x2 - x1, y2 - y1)  # may move up to ~3/4 of its own size between cycles
            best, best_distance = None, reach
            for track in unmatched:
                distance = math.dist(track.centroid, centroid)
                if distance <= best_distance:
                    best, best_distance = track, distance
            if best is not None:
                unmatched.remove(best)
                best.centroid, best.last_seen = centroid, now
            else:
                self.tracks.append(Track(self._next_id, centroid, now, now))
                self._next_id += 1
        return self.tracks


class ActivityMonitor:
    """Restricted-zone and suspicious-activity rules for one camera.

    Rules (all heuristics — what is "suspicious" depends on the place):
      * restricted zone: a person's feet are inside an active zone for
        `zone_confirmations` detection cycles in a row;
      * loitering: one person continuously in view for `loiter_seconds`;
      * after hours: any person during the configured quiet hours (off by default).
    Each rule has a cooldown so a lingering person doesn't flood the alert list.
    """

    def __init__(self, camera_id: str, config: ActivityConfig):
        self.camera_id = camera_id
        self.config = config
        self.zones: list[ZoneSpec] = []
        self._tracker = PersonTracker()
        self._zone_cycles: dict[int, int] = {}
        self._last_alert: dict[tuple, float] = {}

    def set_zones(self, zones: list[ZoneSpec]) -> None:
        self.zones = zones
        self._zone_cycles = {z.id: self._zone_cycles.get(z.id, 0) for z in zones}

    def _cooldown_ok(self, key: tuple, seconds: float, now: float) -> bool:
        last = self._last_alert.get(key)
        if last is not None and now - last < seconds:
            return False
        self._last_alert[key] = now
        return True

    def process(self, detections: list[Detection], frame: np.ndarray, event_id: int | None, now: float | None = None) -> set[int]:
        """Run the rules for one detection cycle. Returns ids of zones with someone inside."""
        now = time.monotonic() if now is None else now
        cfg = self.config
        height, width = frame.shape[:2]
        tracks = self._tracker.update(detections, now)
        occupied = self._check_zones(detections, frame, event_id, now, width, height)

        if cfg.loitering_enabled:
            for track in tracks:
                if track.dwell >= cfg.loiter_seconds and not track.loiter_alerted:
                    track.loiter_alerted = True
                    if self._cooldown_ok(("loitering",), cfg.suspicious_alert_cooldown_seconds, now):
                        self._raise(
                            "suspicious_activity", "medium", f"Loitering: a person has been in view for {int(track.dwell)} s",
                            {"rule": "loitering", "dwell_seconds": int(track.dwell)}, frame, detections, event_id, "suspicious",
                        )

        if cfg.after_hours_enabled and detections and in_window(datetime.now().time(), cfg.after_hours_start, cfg.after_hours_end):
            if self._cooldown_ok(("after_hours",), cfg.suspicious_alert_cooldown_seconds, now):
                self._raise(
                    "suspicious_activity", "medium", "Person detected during quiet hours",
                    {"rule": "after_hours", "window": f"{cfg.after_hours_start}-{cfg.after_hours_end}"}, frame, detections, event_id, "suspicious",
                )
        return occupied

    def _check_zones(self, detections, frame, event_id, now, width, height) -> set[int]:
        occupied: set[int] = set()
        for zone in self.zones:
            if not zone.is_active():
                self._zone_cycles[zone.id] = 0
                continue
            # A person's position on the floor is where their feet are: bottom-centre of the box.
            inside = any(zone.contains((d.bbox[0] + d.bbox[2]) / 2, d.bbox[3], width, height) for d in detections)
            if not inside:
                self._zone_cycles[zone.id] = 0
                continue
            occupied.add(zone.id)
            self._zone_cycles[zone.id] = self._zone_cycles.get(zone.id, 0) + 1
            if self._zone_cycles[zone.id] >= self.config.zone_confirmations and self._cooldown_ok(
                ("zone", zone.id), self.config.zone_alert_cooldown_seconds, now
            ):
                self._raise(
                    "restricted_area", zone.severity, f"Person detected in restricted area: {zone.name}",
                    {"zone": zone.name, "zone_id": zone.id}, frame, detections, event_id, "restricted", highlight={zone.id},
                )
        return occupied

    def _raise(self, alert_type, severity, message, details, frame, detections, event_id, prefix, highlight=None) -> None:
        when = datetime.now(timezone.utc)
        snapshot_rel = None
        try:
            annotated = frame.copy()
            draw_zones(annotated, self.zones, highlight)
            for d in detections:
                cv2.rectangle(annotated, (d.bbox[0], d.bbox[1]), (d.bbox[2], d.bbox[3]), (0, 0, 255), 2)
            path = new_snapshot_path(self.camera_id, when, prefix)
            write_private_jpeg(resolve(str(path)), annotated)
            snapshot_rel = str(path)
        except Exception:
            logger.exception("Camera %s: could not save %s snapshot", self.camera_id, prefix)

        if event_id is not None:
            with SessionLocal() as session:
                event = session.get(Event, event_id)
                if event is not None:
                    upgrade_event_type(event, alert_type)
                    session.commit()
        raise_alert(
            alert_type=alert_type, severity=severity, camera_id=self.camera_id, message=message,
            event_id=event_id, snapshot_path=snapshot_rel, details=details,
        )
