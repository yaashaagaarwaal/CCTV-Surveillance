"""Runs scripted people through the real MotionEventPipeline (motion -> recording ->
person detection -> activity rules) with a fake detector and a fake clock, to check
the rules are wired into the live path: alerts link to the recording's event and the
event is flagged. YOLO is replaced because synthetic video can't contain a person.

Run:  python -m tests.test_activity_pipeline
"""
import json
import os
import tempfile
import time

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import Alert, Camera, Event  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.activity.rules import RulesSpec  # noqa: E402
from app.services.activity.zones import ZoneSpec  # noqa: E402
from app.services.detection.detector import Detection  # noqa: E402
from app.services.recording.pipeline import MotionEventPipeline  # noqa: E402

FPS = settings.capture_fps
STANDING = (300, 200, 360, 380)
LYING = (290, 330, 470, 380)


class ScriptedDetector:
    """Stands in for YOLO: returns whatever the script says for the current fake time."""

    def __init__(self, clock, script):
        self.clock, self.script = clock, script

    def detect(self, frame, confidence=None):
        for start, end, box in self.script:
            if start <= self.clock["t"] - self.clock["origin"] < end:
                return [Detection(box, 0.9)]
        return []


def run(script, seconds, zones=(), rules=RulesSpec()):
    clock = {"t": 5000.0, "origin": 5000.0 + 2.0}  # script times start after a 2 s empty lead-in
    real_monotonic = time.monotonic
    time.monotonic = lambda: clock["t"]
    try:
        pipeline = MotionEventPipeline("cam1", ScriptedDetector(clock, script), None)
        pipeline.set_zones(list(zones))
        pipeline.set_rules(rules)
        rng = np.random.default_rng(0)
        base = np.full((480, 640, 3), 120, np.uint8)
        for i in range(int((seconds + 2) * FPS)):
            frame = base.copy()
            if clock["t"] - clock["origin"] >= -0.5:  # something starts moving: triggers motion
                x = (i * 9) % 500
                frame[300:420, x : x + 100] = rng.integers(0, 255, (120, 100, 3), dtype=np.uint8)
            pipeline.process(frame)
            clock["t"] += 1 / FPS
        pipeline.close()
    finally:
        time.monotonic = real_monotonic


def alerts():
    with SessionLocal() as db:
        return [(a.type, a.severity, json.loads(a.details)["rule"], a.event_id, a.message) for a in db.scalars(select(Alert).order_by(Alert.id))]


def clear():
    with SessionLocal() as db:
        for model in (Alert, Event):
            for row in db.scalars(select(model)):
                db.delete(row)
        db.commit()


def test_fall_through_pipeline():
    clear()
    run([(0, 4, STANDING), (4, 14, LYING)], 15, rules=RulesSpec(fall_enabled=True))
    found = alerts()
    assert [a[2] for a in found] == ["fall_like"], found
    type_, severity, _, event_id, message = found[0]
    assert type_ == "suspicious_activity" and event_id is not None and "Possible fall" in message
    with SessionLocal() as db:
        event = db.get(Event, event_id)
        assert event.event_type == "suspicious_activity" and event.recording_path, "the event is flagged and has a recording"


def test_fall_off_by_default_through_pipeline():
    clear()
    run([(0, 4, STANDING), (4, 14, LYING)], 15)
    assert alerts() == []


def test_zone_rules_through_pipeline():
    clear()
    zone = ZoneSpec(1, "Garden", ((0, 0), (1, 0), (1, 1), (0, 1)), "high", None, None, loiter_seconds=5, repeat_entries=2, repeat_window_seconds=120)
    # Two visits, 8 s apart (YOLO finds nobody in between).
    run([(0, 8, STANDING), (16, 24, STANDING)], 26, zones=[zone])
    rules = [a[2] for a in alerts()]
    assert rules[:2] == ["zone_intrusion", "loitering"] and "repeated_entry" in rules, rules
    assert all(a[3] is not None for a in alerts()), "every alert links to its recording event"
    with SessionLocal() as db:
        assert {e.event_type for e in db.scalars(select(Event))} <= {"restricted_area", "suspicious_activity"}


def main() -> int:
    init_db()
    with SessionLocal() as db:
        db.add(Camera(id="cam1", name="Test cam", type="file", source="x"))
        db.commit()
    failures = 0
    for name, func in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        try:
            func()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print("pipeline wiring ok" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
