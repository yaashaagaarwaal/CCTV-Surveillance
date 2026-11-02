"""Fire and smoke alerts from the fire/smoke model's boxes.

The model only says "this box looks like fire/smoke, N % sure" for one frame. This module turns that into something
safe to raise an alarm on, with plain rules and no hidden state:

  * fire and smoke are judged SEPARATELY (own thresholds, own counters, own cooldown, own alert type);
  * a class is CONFIRMED only after `confirm_hits` detection cycles inside `confirm_window_seconds`; one frame never alerts;
  * one alert per episode (it ends after `clear_seconds` without a detection), and never inside the cooldown;
    a confirmation that falls inside the cooldown is held back, not lost: it alerts when the cooldown ends if it is still there;
  * a camera outage ends the episode (`interrupt()`): nothing is counted across a gap.

Alerts go through raise_alert() like every other alert: camera, time, confidence, type and snapshot are stored, and the
details explain exactly why it fired. The pure logic (`update`) takes the clock as an argument so it is testable without waiting.
"""
import logging
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

import cv2
import numpy as np

from app.core.config import FireConfig
from app.db.models import Event
from app.db.session import SessionLocal
from app.services.alerts import raise_alert
from app.services.detection.fire import KINDS, FireDetection
from app.services.faces.storage import new_snapshot_path, resolve, write_private_jpeg
from app.services.recording.event_types import upgrade_event_type

logger = logging.getLogger(__name__)

SEVERITY = {"fire": "critical", "smoke": "high"}
BOX_COLOR = {"fire": (0, 90, 255), "smoke": (190, 190, 190)}  # BGR: orange-red, grey
NOTE = (
    "Estimated by a small AI model from one camera picture. Red lamps, sunsets, steam, fog or a screen showing flames can look "
    "like fire or smoke, and real smoke can be missed. Check the camera and the room before acting."
)
VISIBLE_SECONDS = 3.0  # how long the last boxes stay on the live picture


@dataclass
class Confirmed:
    kind: str
    confidence: float  # best seen inside the window
    hits: int
    boxes: list[tuple[int, int, int, int]]


class _KindState:
    def __init__(self):
        self.hits: deque[tuple[float, float]] = deque()  # (time, best confidence of that cycle)
        self.last_seen: float | None = None
        self.last_alert: float | None = None
        self.active = False  # an alert for the current episode has been raised
        self.boxes: list[tuple[int, int, int, int]] = []

    def reset_episode(self):
        self.hits.clear()
        self.active = False
        self.boxes = []


class FireMonitor:
    """Per camera. Fed one list of detections per detection cycle by the pipeline's analysis thread."""

    def __init__(self, camera_id: str, config: FireConfig):
        self.camera_id = camera_id
        self.config = config
        self._state = {kind: _KindState() for kind in KINDS}
        self._needed = {"fire": config.fire_confirm_hits, "smoke": config.smoke_confirm_hits}
        self._cooldown = {"fire": config.fire_alert_cooldown_seconds, "smoke": config.smoke_alert_cooldown_seconds}

    # --- pure logic ---------------------------------------------------------------------------------------------
    def update(self, detections: list[FireDetection], now: float) -> list[Confirmed]:
        """One detection cycle. Returns the classes that just became confirmed AND are allowed to alert (not in cooldown)."""
        cfg = self.config
        confirmed = []
        for kind in KINDS:
            state = self._state[kind]
            if state.active and state.last_seen is not None and now - state.last_seen >= cfg.clear_seconds:
                state.reset_episode()  # it went away: whatever is seen next is a new episode (checked first, so it never depends on empty cycles being fed in)
            mine = [d for d in detections if d.kind == kind]
            if mine:
                state.last_seen = now
                state.hits.append((now, max(d.confidence for d in mine)))
                state.boxes = [d.bbox for d in mine]
            while state.hits and now - state.hits[0][0] > cfg.confirm_window_seconds:
                state.hits.popleft()
            if state.active or len(state.hits) < self._needed[kind]:
                continue
            if state.last_alert is not None and now - state.last_alert < self._cooldown[kind]:
                continue  # held back, not forgotten: it alerts when the cooldown ends if it is still being seen
            state.active = True
            state.last_alert = now
            confirmed.append(Confirmed(kind, round(max(c for _, c in state.hits), 2), len(state.hits), list(state.boxes)))
        return confirmed

    def interrupt(self) -> None:
        """Camera lost: nothing counted before the gap may combine with anything after it. Cooldowns are kept."""
        for state in self._state.values():
            state.reset_episode()
            state.last_seen = None

    def episode_active(self) -> bool:
        return any(state.active for state in self._state.values())

    def status(self, now: float | None = None) -> dict:
        """Live state for the camera tile: per class, whether it is being seen right now and how far confirmation is."""
        now = time.monotonic() if now is None else now
        out = {}
        for kind in KINDS:
            state = self._state[kind]
            recent = [h for h in state.hits if now - h[0] <= self.config.confirm_window_seconds]
            out[kind] = {
                "seen": state.last_seen is not None and now - state.last_seen <= VISIBLE_SECONDS,
                "hits": len(recent),
                "needed": self._needed[kind],
                "active": state.active,
                "confidence": round(max(c for _, c in recent), 2) if recent else None,
            }
        return out

    # --- the alert ----------------------------------------------------------------------------------------------
    def alert(self, found: Confirmed, frame: np.ndarray, event_id: int | None) -> int | None:
        """Raise the alert for a confirmed class; returns the alert id (None only if raising itself failed)."""
        cfg = self.config
        when = datetime.now(timezone.utc)
        snapshot_rel = None
        try:
            picture = frame.copy()
            draw_boxes(picture, [FireDetection(found.kind, box, found.confidence) for box in found.boxes])
            path = new_snapshot_path(self.camera_id, when, found.kind)
            write_private_jpeg(resolve(str(path)), picture)
            snapshot_rel = str(path)
        except Exception:
            logger.exception("Camera %s: could not save the %s snapshot", self.camera_id, found.kind)

        if event_id is not None:
            try:
                with SessionLocal() as session:
                    event = session.get(Event, event_id)
                    if event is not None:
                        upgrade_event_type(event, found.kind)
                        if event.max_confidence is None or found.confidence > event.max_confidence:
                            event.max_confidence = found.confidence
                        session.commit()
            except Exception:
                logger.exception("Camera %s: could not mark event %s as %s", self.camera_id, event_id, found.kind)

        explanation = (
            f"{found.kind.capitalize()} was detected in {found.hits} checks within {cfg.confirm_window_seconds:.0f} s "
            f"(best confidence {found.confidence:.0%}; needs {self._needed[found.kind]} checks)."
        )
        try:
            return raise_alert(
                alert_type=found.kind,
                severity=SEVERITY[found.kind],
                camera_id=self.camera_id,
                message=f"{found.kind.capitalize()} detected ({found.confidence:.0%} confidence)",
                event_id=event_id,
                snapshot_path=snapshot_rel,
                details={
                    "rule": found.kind,
                    "kind": found.kind,
                    "confidence": found.confidence,
                    "confirmations": found.hits,
                    "window_seconds": cfg.confirm_window_seconds,
                    "boxes": [list(b) for b in found.boxes],
                    "explanation": explanation,
                    "confidence_note": NOTE,
                },
            )
        except Exception:
            logger.exception("Camera %s: could not raise the %s alert", self.camera_id, found.kind)
            return None


def draw_boxes(frame: np.ndarray, detections: list[FireDetection]) -> None:
    for d in detections:
        x1, y1, x2, y2 = d.bbox
        color = BOX_COLOR[d.kind]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(frame, f"{d.kind} {d.confidence:.0%}", (x1, max(y1 - 8, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
