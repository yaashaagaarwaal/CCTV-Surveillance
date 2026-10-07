"""Tests every suspicious-activity rule with scripted people and a controlled clock
(no camera, no YOLO), against a throwaway database and the real alert pipeline.

Run:  python -m tests.test_activity_rules      (or with pytest)
"""
import json
import os
import tempfile
from datetime import datetime

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"

import numpy as np  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.core.config import ActivityConfig  # noqa: E402
from app.db.models import Alert, Camera, Event  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.activity.monitor import ActivityMonitor  # noqa: E402
from app.services.activity.rules import RulesSpec  # noqa: E402
from app.services.activity.zones import ZoneSpec  # noqa: E402
from app.services.detection.detector import Detection  # noqa: E402

FRAME = np.zeros((480, 640, 3), np.uint8)
STEP = 0.5  # seconds between detection cycles
NOON = datetime(2025, 1, 15, 12, 0)
NIGHT = datetime(2025, 1, 15, 2, 30)

# The right half of the picture is the restricted zone.
RIGHT_HALF = ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0))
INSIDE = Detection((400, 200, 460, 380), 0.9)  # feet at (430, 380): inside
OUTSIDE = Detection((100, 200, 160, 380), 0.8)


def zone(**kw) -> ZoneSpec:
    base = dict(id=1, name="Driveway", points=RIGHT_HALF, severity="high", schedule_start=None, schedule_end=None,
                loiter_seconds=10, repeat_entries=3, repeat_window_seconds=120)
    return ZoneSpec(**{**base, **kw})


def monitor(zones=(), rules=RulesSpec(), **config) -> ActivityMonitor:
    cfg = ActivityConfig(**{"zone_alert_cooldown_seconds": 1.0, "suspicious_alert_cooldown_seconds": 1.0, **config})
    m = ActivityMonitor("cam1", cfg)
    m.set_zones(list(zones))
    m.set_rules(rules)
    return m


class Clock:
    """Feeds cycles to a monitor, tracking time."""

    def __init__(self, m: ActivityMonitor, wall: datetime = NOON, start: float = 1000.0):
        self.m, self.t, self.wall = m, start, wall

    def run(self, seconds: float, detections=(), event_id=None) -> None:
        for _ in range(round(seconds / STEP)):
            self.t += STEP
            self.m.process(list(detections), FRAME, event_id, now=self.t, wall=self.wall)

    def skip(self, seconds: float) -> None:  # nothing processed, e.g. no motion so no detection cycles
        self.t += seconds


def fresh_alerts() -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(select(Alert).order_by(Alert.id)).all()
        out = [
            {"type": a.type, "severity": a.severity, "message": a.message, "details": json.loads(a.details), "snapshot": a.snapshot_path, "event_id": a.event_id}
            for a in rows
        ]
        db.execute(delete(Alert))
        db.commit()
    return out


def rules_of(alerts) -> list[str]:
    return [a["details"]["rule"] for a in alerts]


def standing(x=0, h=180, w=60, bottom=380):
    return Detection((300 + x, bottom - h, 300 + x + w, bottom), 0.85)


def test_intrusion():
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=0)]))
    c.run(5, [OUTSIDE])
    assert fresh_alerts() == [], "a person outside the zone must not alert"
    c.run(STEP, [INSIDE])
    assert fresh_alerts() == [], "one cycle inside is not enough (needs confirmation)"
    c.run(STEP * 3, [INSIDE])
    (alert,) = fresh_alerts()
    assert alert["type"] == "restricted_area" and alert["severity"] == "high"
    assert alert["details"]["rule"] == "zone_intrusion" and alert["details"]["zone"] == "Driveway"
    assert alert["details"]["confidence"] == 0.9
    assert "Driveway" in alert["message"] and alert["snapshot"], "has an explanation and a snapshot"
    c.run(30, [INSIDE])
    assert fresh_alerts() == [], "staying inside must not alert again (one alert per entry)"


def test_flicker_not_confirmed():
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=0)]))
    for _ in range(6):
        c.run(STEP, [INSIDE])
        c.run(STEP, [OUTSIDE])  # a one-cycle false positive, then gone
    assert fresh_alerts() == [], "isolated single-cycle detections must be ignored"


def test_zone_schedule():
    sched = zone(schedule_start="22:00", schedule_end="06:00", loiter_seconds=0, repeat_entries=0)
    c = Clock(monitor([sched]), wall=NOON)
    c.run(5, [INSIDE])
    assert fresh_alerts() == [], "outside the zone's schedule nothing is enforced"
    c = Clock(monitor([sched]), wall=NIGHT)
    c.run(5, [INSIDE])
    (alert,) = fresh_alerts()
    assert "22:00" in alert["message"], "the schedule is part of the explanation"


def test_loitering_in_zone():
    c = Clock(monitor([zone(repeat_entries=0)]))
    c.run(9, [INSIDE])
    assert rules_of(fresh_alerts()) == ["zone_intrusion"], "under the limit: only the intrusion"
    c.run(3, [INSIDE])
    (alert,) = fresh_alerts()
    d = alert["details"]
    assert d["rule"] == "loitering" and alert["type"] == "suspicious_activity" and alert["severity"] == "high"
    assert d["threshold_seconds"] == 10 and 10 <= d["dwell_seconds"] <= 12
    assert f"{d['dwell_seconds']} seconds" in alert["message"] and "Driveway" in alert["message"]
    c.run(20, [INSIDE])
    assert fresh_alerts() == [], "one loitering alert per visit"
    # Leaving and coming back is a new visit and can loiter again.
    c.run(6, [OUTSIDE])
    c.run(14, [INSIDE])
    assert rules_of(fresh_alerts()) == ["zone_intrusion", "loitering"]


def test_loitering_off_and_other_zone():
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=0)]))
    c.run(60, [INSIDE])
    assert rules_of(fresh_alerts()) == ["zone_intrusion"], "loiter_seconds=0 turns the rule off"
    # Dwell is per zone: walking inside a different place doesn't count towards this one.
    c = Clock(monitor([zone(loiter_seconds=10, repeat_entries=0)]))
    c.run(60, [OUTSIDE])
    assert fresh_alerts() == []


def test_brief_dropout_keeps_visit():
    """A missed detection (person briefly hidden) must not restart the dwell timer."""
    c = Clock(monitor([zone(repeat_entries=0)]))
    c.run(6, [INSIDE])
    c.run(STEP, [])  # one missed cycle
    c.run(6, [INSIDE])
    assert rules_of(fresh_alerts()) == ["zone_intrusion", "loitering"]


def test_repeated_entry():
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=3, repeat_window_seconds=120)]))
    for _ in range(2):
        c.run(3, [INSIDE])
        c.run(8, [OUTSIDE])  # out of the zone longer than the exit grace
    assert rules_of(fresh_alerts()) == ["zone_intrusion", "zone_intrusion"], "two entries: not yet repeated"
    c.run(3, [INSIDE])
    alerts = fresh_alerts()
    assert rules_of(alerts) == ["zone_intrusion", "repeated_entry"]
    repeated = alerts[1]
    assert repeated["type"] == "suspicious_activity" and repeated["severity"] == "critical", "escalated one level from high"
    assert repeated["details"]["entries"] == 3 and repeated["details"]["window_seconds"] == 120
    assert "3 times" in repeated["message"]
    # A fresh run is needed to alert again.
    c.run(8, [OUTSIDE])
    c.run(3, [INSIDE])
    assert "repeated_entry" not in rules_of(fresh_alerts())


def test_repeated_entry_outside_window_and_no_exit():
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=3, repeat_window_seconds=60)]))
    for _ in range(3):
        c.run(3, [INSIDE])
        c.run(40, [OUTSIDE])  # slower than the window allows
    assert "repeated_entry" not in rules_of(fresh_alerts()), "entries spread over more than the window don't count"
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=2, repeat_window_seconds=60)]))
    c.run(3, [INSIDE])
    c.run(2, [OUTSIDE])  # shorter than the exit grace: still the same visit
    c.run(3, [INSIDE])
    assert "repeated_entry" not in rules_of(fresh_alerts()), "stepping out for a moment is not a new entry"


def test_idle_gap_counts_as_leaving():
    """When the camera stops detecting (no motion), time still passes."""
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=2, repeat_window_seconds=300)]))
    c.run(3, [INSIDE])
    c.skip(60)
    c.run(3, [INSIDE])
    assert rules_of(fresh_alerts())[-1] == "repeated_entry"


def test_security_hours():
    rules = RulesSpec("23:00", "05:00")
    c = Clock(monitor(rules=rules, suspicious_alert_cooldown_seconds=60.0), wall=NIGHT)
    c.run(2, [])
    assert fresh_alerts() == [], "nobody there, nothing to report"
    c.run(2, [OUTSIDE])
    (alert,) = fresh_alerts()
    assert alert["details"]["rule"] == "after_hours" and alert["severity"] == "medium"
    assert "02:30" in alert["message"] and "23:00" in alert["message"]
    c.run(30, [OUTSIDE])
    assert fresh_alerts() == [], "bounded by the cooldown"
    c = Clock(monitor(rules=rules), wall=NOON)
    c.run(10, [OUTSIDE])
    assert fresh_alerts() == [], "a person at noon is outside the hours"
    c = Clock(monitor(rules=RulesSpec()), wall=NIGHT)
    c.run(10, [OUTSIDE])
    assert fresh_alerts() == [], "no hours configured = rule off"
    # A daytime window (does not cross midnight).
    c = Clock(monitor(rules=RulesSpec("09:00", "17:00"), suspicious_alert_cooldown_seconds=60.0), wall=NOON)
    c.run(2, [OUTSIDE])
    assert rules_of(fresh_alerts()) == ["after_hours"]


def test_security_hours_cooldown():
    c = Clock(monitor(rules=RulesSpec("23:00", "05:00"), suspicious_alert_cooldown_seconds=60.0), wall=NIGHT)
    c.run(50, [OUTSIDE])
    assert len(fresh_alerts()) == 1
    c.run(20, [OUTSIDE])
    assert len(fresh_alerts()) == 1, "a second alert after the cooldown"


def test_fall_like():
    rules = RulesSpec(fall_enabled=True)

    def fall(c, lying_seconds=6):
        c.run(3, [standing()])
        c.run(STEP, [Detection((290, 330, 470, 380), 0.8)])  # now wide and low: bottom stays, top drops
        c.run(lying_seconds, [Detection((290, 330, 470, 380), 0.8)])

    c = Clock(monitor(rules=rules))
    fall(c)
    (alert,) = fresh_alerts()
    d = alert["details"]
    assert d["rule"] == "fall_like" and alert["severity"] == "medium" and alert["type"] == "suspicious_activity"
    assert d["change_seconds"] <= 3 and d["down_seconds"] >= 4 and d["height_drop_percent"] >= 35
    assert "Possible fall" in alert["message"] and d["note"], "worded as a possibility, with its limitation"

    c = Clock(monitor(rules=RulesSpec(fall_enabled=False)))
    fall(c)
    assert fresh_alerts() == [], "off unless enabled for the camera"

    c = Clock(monitor(rules=rules))
    c.run(3, [standing()])
    c.run(STEP, [Detection((290, 330, 470, 380), 0.8)])
    c.run(2, [Detection((290, 330, 470, 380), 0.8)])
    c.run(4, [standing()])  # got back up before the confirm time
    assert fresh_alerts() == [], "getting back up quickly is not an alert"


def test_fall_false_positives():
    rules = RulesSpec(fall_enabled=True)
    lying = Detection((290, 330, 470, 380), 0.8)

    c = Clock(monitor(rules=rules))
    c.run(30, [lying])
    assert fresh_alerts() == [], "first seen already lying (e.g. asleep): no sudden change was observed"

    c = Clock(monitor(rules=rules))
    c.run(3, [standing()])
    c.run(15, [Detection((300, 280, 360, 380), 0.8)])  # sat down: shorter but still taller than wide
    assert fresh_alerts() == [], "sitting is not lying"

    c = Clock(monitor(rules=rules))
    c.run(3, [standing()])
    for i in range(1, 11):  # slowly lowers over 10 s
        c.run(1, [Detection((300, 380 - round(180 - i * 13.5), 360 + i * 12, 380), 0.8)])
    c.run(8, [lying])
    assert fresh_alerts() == [], "a slow change over many seconds is not sudden"

    c = Clock(monitor(rules=rules))
    c.run(3, [standing(h=40, w=14, bottom=100)])  # a tiny far-away figure
    c.run(8, [Detection((300, 80, 345, 100), 0.8)])
    assert fresh_alerts() == [], "tiny, far-away boxes are too noisy to judge"

    c = Clock(monitor(rules=rules))
    for k in range(20):  # walking across the picture, upright throughout
        c.run(STEP, [standing(x=k * 10)])
    assert fresh_alerts() == []


def test_lingering_in_view():
    c = Clock(monitor(lingering_enabled=True, lingering_seconds=20.0))
    c.run(15, [OUTSIDE])
    assert fresh_alerts() == []
    c.run(10, [OUTSIDE])
    (alert,) = fresh_alerts()
    assert alert["details"]["rule"] == "lingering" and alert["details"]["dwell_seconds"] >= 20
    c = Clock(monitor())
    c.run(120, [OUTSIDE])
    assert fresh_alerts() == [], "off by default"


def test_event_type_upgrade_and_isolation():
    with SessionLocal() as db:
        event = Event(camera_id="cam1", event_type="person", status="recording")
        db.add(event)
        db.commit()
        event_id = event.id
    c = Clock(monitor([zone()]))
    c.run(5, [INSIDE], event_id=event_id)
    alerts = fresh_alerts()
    assert all(a["event_id"] == event_id for a in alerts), "alerts link to the recording's event"
    with SessionLocal() as db:
        assert db.get(Event, event_id).event_type == "restricted_area"
    # Zones on different cameras / zones don't share state.
    a, b = zone(id=1, name="A", points=((0.5, 0), (1, 0), (1, 1), (0.5, 1))), zone(id=2, name="B", points=((0, 0), (0.4, 0), (0.4, 1), (0, 1)), loiter_seconds=0, repeat_entries=0)
    c = Clock(monitor([a, b]))
    c.run(3, [INSIDE])
    names = [x["details"]["zone"] for x in fresh_alerts() if "zone" in x["details"]]
    assert names == ["A"]


def test_zone_reload_keeps_working():
    c = Clock(monitor([zone(loiter_seconds=0, repeat_entries=0)]))
    c.run(3, [INSIDE])
    fresh_alerts()
    c.m.set_zones([])  # zone deleted while someone is inside
    c.run(3, [INSIDE])
    assert fresh_alerts() == []


def main() -> int:
    init_db()
    with SessionLocal() as db:
        db.add(Camera(id="cam1", name="Test cam", type="file", source="x"))
        db.commit()
    failures = 0
    for name, func in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and n != "test_all_rules" and callable(f)):
        try:
            func()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print("all rules pass" if not failures else f"{failures} failed")
    return 1 if failures else 0


def test_all_rules():  # lets pytest run everything through the shared setup
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
