import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np

from app.core.config import ActivityConfig
from app.db.models import Event
from app.db.session import SessionLocal
from app.services.activity.posture import PostureState
from app.services.activity.rules import RulesSpec
from app.services.activity.zones import ZoneSpec, draw_zones, in_window
from app.services.alerts import SEVERITIES, raise_alert
from app.services.detection.detector import Detection
from app.services.faces.storage import new_snapshot_path, resolve, write_private_jpeg
from app.services.recording.event_types import upgrade_event_type

logger = logging.getLogger(__name__)

TRACK_TIMEOUT_SECONDS = 4.0
CONFIDENCE_NOTE = "person detector confidence"


def escalate(severity: str) -> str:
    """One level more serious, capped at critical."""
    return SEVERITIES[min(SEVERITIES.index(severity) + 1, len(SEVERITIES) - 1)]


def duration_text(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{seconds // 60} min {seconds % 60} s" if seconds % 60 else f"{seconds // 60} minutes"


@dataclass
class Track:
    id: int
    centroid: tuple[float, float]
    first_seen: float
    last_seen: float
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    lingering_alerted: bool = False
    posture: PostureState = field(default_factory=PostureState)

    @property
    def dwell(self) -> float:
        return self.last_seen - self.first_seen


@dataclass
class PersonTracker:
    """Follows people between detection cycles by nearest-centroid matching.
    Deliberately simple: it only has to answer "is this the same person as a
    moment ago?" for dwell time and posture change, not tell individuals apart
    in a crowd."""

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
                track = best
                track.centroid, track.last_seen = centroid, now
            else:
                track = Track(self._next_id, centroid, now, now)
                self.tracks.append(track)
                self._next_id += 1
            track.bbox, track.confidence = det.bbox, det.confidence
        return self.tracks


@dataclass
class ZoneState:
    """Where one zone stands: is someone in it, since when, and the recent entries."""

    cycles: int = 0  # consecutive cycles with someone inside, until the entry is confirmed
    visit_started: float = 0.0
    last_inside: float | None = None
    inside: bool = False  # a confirmed entry is in progress
    loiter_alerted: bool = False
    entries: deque = field(default_factory=deque)  # times of confirmed entries


class ActivityMonitor:
    """Restricted-zone and suspicious-activity rules for one camera.

    Every rule is a plain, explainable condition, and every alert says which
    condition fired and with what numbers. None of this judges intent: what is
    suspicious depends on the place and the household.

      * zone intrusion      a person's feet are inside an active zone for
                            `zone_confirmations` detection cycles in a row;
      * zone loitering      someone stays inside one zone for its `loiter_seconds`;
      * repeated entry      a zone is entered `repeat_entries` times within
                            `repeat_window_seconds` (leaving = empty for `zone_exit_seconds`);
      * security hours      a person is seen during the camera's configured hours;
      * fall-like           see posture.py (off unless enabled for the camera);
      * lingering in view   one person in view for a long time anywhere (optional).
    Each rule has a cooldown so a lingering person doesn't flood the alert list.
    """

    def __init__(self, camera_id: str, config: ActivityConfig):
        self.camera_id = camera_id
        self.config = config
        self.zones: list[ZoneSpec] = []
        self.rules = RulesSpec()
        self._tracker = PersonTracker()
        self._zone_state: dict[int, ZoneState] = {}
        self._last_alert: dict[tuple, float] = {}

    def set_zones(self, zones: list[ZoneSpec]) -> None:
        self.zones = zones
        self._zone_state = {z.id: self._zone_state.get(z.id, ZoneState()) for z in zones}

    def set_rules(self, rules: RulesSpec) -> None:
        self.rules = rules

    def _cooldown_ok(self, key: tuple, seconds: float, now: float) -> bool:
        last = self._last_alert.get(key)
        if last is not None and now - last < seconds:
            return False
        self._last_alert[key] = now
        return True

    def process(
        self, detections: list[Detection], frame: np.ndarray, event_id: int | None, now: float | None = None, wall: datetime | None = None
    ) -> set[int]:
        """Run the rules for one detection cycle (call it every cycle, also when
        nobody is found). Returns ids of zones with someone inside.

        `now` is a monotonic clock for durations and `wall` the local time for
        schedules/security hours; both can be passed in so tests control time."""
        now = time.monotonic() if now is None else now
        wall = datetime.now() if wall is None else wall
        cfg = self.config
        height, width = frame.shape[:2]
        tracks = self._tracker.update(detections, now)
        occupied = self._check_zones(detections, frame, event_id, now, wall, width, height)

        if cfg.lingering_enabled:
            for track in tracks:
                if track.last_seen == now and track.dwell >= cfg.lingering_seconds and not track.lingering_alerted:
                    track.lingering_alerted = True
                    if self._cooldown_ok(("lingering",), cfg.suspicious_alert_cooldown_seconds, now):
                        self._raise(
                            "suspicious_activity", "medium", "lingering",
                            f"A person has been in view for {duration_text(track.dwell)} (camera-wide limit {duration_text(cfg.lingering_seconds)})",
                            {"dwell_seconds": int(track.dwell), "threshold_seconds": int(cfg.lingering_seconds)},
                            frame, detections, event_id, [track.confidence],
                        )

        if self.rules.has_quiet_hours and detections and in_window(wall.time(), self.rules.quiet_start, self.rules.quiet_end):
            if self._cooldown_ok(("after_hours",), cfg.suspicious_alert_cooldown_seconds, now):
                self._raise(
                    "suspicious_activity", "medium", "after_hours",
                    f"Person detected at {wall:%H:%M}, within security hours {self.rules.quiet_start}–{self.rules.quiet_end}",
                    {"local_time": f"{wall:%H:%M}", "quiet_hours": f"{self.rules.quiet_start}-{self.rules.quiet_end}"},
                    frame, detections, event_id, [d.confidence for d in detections],
                )

        if self.rules.fall_enabled:
            self._check_falls(tracks, frame, detections, event_id, now, height)
        return occupied

    def _check_falls(self, tracks, frame, detections, event_id, now, frame_height) -> None:
        cfg = self.config
        for track in tracks:
            if track.last_seen != now:
                continue  # not seen this cycle
            x1, y1, x2, y2 = track.bbox
            fall = track.posture.update(x2 - x1, y2 - y1, (y1 + y2) / 2, now, frame_height, cfg)
            if fall is not None and self._cooldown_ok(("fall",), cfg.fall_cooldown_seconds, now):
                self._raise(
                    "suspicious_activity", "medium", "fall_like",
                    f"Possible fall: a person went from standing to lying within {fall.change_seconds:.1f} s "
                    f"and has stayed down for {fall.down_seconds:.0f} s",
                    {
                        "change_seconds": round(fall.change_seconds, 1), "down_seconds": round(fall.down_seconds),
                        "height_drop_percent": round(fall.height_drop * 100),
                        "note": "Estimated from the person's outline only, so it can be wrong.",
                    },
                    frame, detections, event_id, [track.confidence],
                )

    def _check_zones(self, detections, frame, event_id, now, wall, width, height) -> set[int]:
        cfg = self.config
        occupied: set[int] = set()
        for zone in self.zones:
            state = self._zone_state.setdefault(zone.id, ZoneState())
            if not zone.is_active(wall):
                self._zone_state[zone.id] = ZoneState()
                continue
            # A person's position on the floor is where their feet are: bottom-centre of the box.
            inside = [d for d in detections if zone.contains((d.bbox[0] + d.bbox[2]) / 2, d.bbox[3], width, height)]
            if not inside:
                if not state.inside:
                    state.cycles = 0  # confirmation needs consecutive cycles
                elif now - (state.last_inside or now) > cfg.zone_exit_seconds:
                    state.inside = False  # empty long enough: they left
                    state.cycles = 0
                continue

            occupied.add(zone.id)
            if state.last_inside is not None and now - state.last_inside > cfg.zone_exit_seconds:
                state.inside, state.cycles, state.loiter_alerted = False, 0, False  # a new visit
            state.last_inside = now
            if state.cycles == 0:
                state.visit_started = now
            state.cycles += 1
            confidences = [d.confidence for d in inside]

            if not state.inside and state.cycles >= cfg.zone_confirmations:
                state.inside, state.loiter_alerted = True, False
                state.entries.append(state.visit_started)
                self._on_entry(zone, state, frame, detections, confidences, event_id, now, wall)

            if state.inside and zone.loiter_seconds > 0 and not state.loiter_alerted and now - state.visit_started >= zone.loiter_seconds:
                state.loiter_alerted = True
                if self._cooldown_ok(("loitering", zone.id), cfg.suspicious_alert_cooldown_seconds, now):
                    dwell = now - state.visit_started
                    self._raise(
                        "suspicious_activity", zone.severity, "loitering",
                        f"Person remained in restricted zone '{zone.name}' for {duration_text(dwell)} (limit {duration_text(zone.loiter_seconds)})",
                        {"zone": zone.name, "zone_id": zone.id, "dwell_seconds": int(dwell), "threshold_seconds": zone.loiter_seconds},
                        frame, detections, event_id, confidences, highlight={zone.id},
                    )
        return occupied

    def _on_entry(self, zone, state, frame, detections, confidences, event_id, now, wall) -> None:
        cfg = self.config
        if self._cooldown_ok(("zone", zone.id), cfg.zone_alert_cooldown_seconds, now):
            schedule = f" (enforced {zone.schedule_start}–{zone.schedule_end})" if zone.schedule_start else ""
            self._raise(
                "restricted_area", zone.severity, "zone_intrusion",
                f"Person entered restricted zone '{zone.name}'{schedule}",
                {"zone": zone.name, "zone_id": zone.id},
                frame, detections, event_id, confidences, highlight={zone.id},
            )

        if zone.repeat_entries > 0:
            while state.entries and now - state.entries[0] > zone.repeat_window_seconds:
                state.entries.popleft()
            count = len(state.entries)
            if count >= zone.repeat_entries and self._cooldown_ok(("repeat", zone.id), zone.repeat_window_seconds, now):
                span = now - state.entries[0]
                self._raise(
                    "suspicious_activity", escalate(zone.severity), "repeated_entry",
                    f"Person entered restricted zone '{zone.name}' {count} times in {duration_text(span)} "
                    f"(alert after {zone.repeat_entries} within {duration_text(zone.repeat_window_seconds)})",
                    {
                        "zone": zone.name, "zone_id": zone.id, "entries": count, "span_seconds": int(span),
                        "threshold_entries": zone.repeat_entries, "window_seconds": zone.repeat_window_seconds,
                    },
                    frame, detections, event_id, confidences, highlight={zone.id},
                )
                state.entries.clear()  # needs a fresh run of entries to alert again

    def _raise(self, alert_type, severity, rule, message, facts, frame, detections, event_id, confidences, highlight=None) -> None:
        when = datetime.now(timezone.utc)
        snapshot_rel = None
        try:
            annotated = frame.copy()
            draw_zones(annotated, self.zones, highlight)
            for d in detections:
                cv2.rectangle(annotated, (d.bbox[0], d.bbox[1]), (d.bbox[2], d.bbox[3]), (0, 0, 255), 2)
            path = new_snapshot_path(self.camera_id, when, rule)
            write_private_jpeg(resolve(str(path)), annotated)
            snapshot_rel = str(path)
        except Exception:
            logger.exception("Camera %s: could not save %s snapshot", self.camera_id, rule)

        if event_id is not None:
            with SessionLocal() as session:
                event = session.get(Event, event_id)
                if event is not None:
                    upgrade_event_type(event, alert_type)
                    session.commit()
        confidence = round(max(confidences), 2) if confidences else None
        raise_alert(
            alert_type=alert_type, severity=severity, camera_id=self.camera_id, message=message,
            event_id=event_id, snapshot_path=snapshot_rel,
            details={"rule": rule, **facts, "confidence": confidence, "confidence_note": CONFIDENCE_NOTE},
        )
