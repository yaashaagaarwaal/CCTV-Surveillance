"""Crowd counting and the crowd alert, with scripted detections and a controlled clock.

Covers: merging duplicate boxes (one person must not count twice), counting inside a zone, the
"approximate" flag, the over-the-limit timer (flicker, dips, gaps), one alert per crowded episode,
the cooldown, camera interruptions, and that a count is never presented as exact.
No camera and no YOLO are involved; the real alert pipeline writes to a throwaway database.

Run:  python -m tests.test_crowd
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
from app.db.models import Alert, Camera  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.activity.crowd import CrowdTimer, count_people, partly_hidden, unique_people  # noqa: E402
from app.services.activity.monitor import ActivityMonitor  # noqa: E402
from app.services.activity.rules import RulesSpec  # noqa: E402
from app.services.activity.zones import ZoneSpec  # noqa: E402
from app.services.detection.detector import Detection  # noqa: E402

FRAME = np.zeros((480, 640, 3), np.uint8)
STEP = 0.5
NOON = datetime(2025, 1, 15, 12, 0)
RIGHT_HALF = ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0))


def person(x: int, conf: float = 0.85, height: int = 180) -> Detection:
    return Detection((x, 380 - height, x + 60, 380), conf)


def group(n: int, start: int = 20, gap: int = 100) -> list[Detection]:
    return [person(start + i * gap) for i in range(n)]


def monitor(threshold=3, seconds=10, zone_id=None, zones=(), **config) -> ActivityMonitor:
    cfg = ActivityConfig(**{"crowd_alert_cooldown_seconds": 60.0, "crowd_grace_seconds": 3.0, **config})
    m = ActivityMonitor("cam1", cfg)
    m.set_zones(list(zones))
    m.set_rules(RulesSpec(crowd_threshold=threshold, crowd_seconds=seconds, crowd_zone_id=zone_id))
    return m


class Clock:
    def __init__(self, m: ActivityMonitor, start: float = 1000.0):
        self.m, self.t = m, start

    def run(self, seconds: float, detections=()) -> None:
        for _ in range(round(seconds / STEP)):
            self.t += STEP
            self.m.process(list(detections), FRAME, None, now=self.t, wall=NOON)

    def skip(self, seconds: float) -> None:
        self.t += seconds


def crowd_alerts(alerts: list[dict]) -> list[dict]:
    return [a for a in alerts if a["details"]["rule"] == "crowd"]


def fresh_alerts() -> list[dict]:
    with SessionLocal() as db:
        rows = db.scalars(select(Alert).order_by(Alert.id)).all()
        out = [{"type": a.type, "severity": a.severity, "message": a.message, "details": json.loads(a.details), "snapshot": a.snapshot_path} for a in rows]
        db.execute(delete(Alert))
        db.commit()
    return out


# ------------------------------------------------------------------ counting


def test_a_second_box_round_the_same_person_is_not_a_second_person():
    tall = Detection((390, 38, 640, 480), 0.76)
    shorter_inside = Detection((400, 170, 640, 480), 0.63)  # what the detector drew in the night benchmark
    other = Detection((0, 170, 320, 480), 0.79)
    assert len(unique_people([tall, shorter_inside])) == 1
    kept = unique_people([shorter_inside, tall, other])
    assert len(kept) == 2 and tall in kept and shorter_inside not in kept, "the stronger box is kept"
    near_copy = Detection((402, 40, 642, 478), 0.5)
    assert len(unique_people([tall, near_copy])) == 1, "an almost identical box (IoU) is the same person"


def test_neighbours_are_two_people_and_overlap_is_flagged():
    a, b = person(100), person(140)  # shoulder to shoulder: the boxes overlap by a third
    assert len(unique_people([a, b])) == 2
    assert partly_hidden([a, b]) is True, "people who overlap may be hiding each other"
    assert partly_hidden([person(50), person(300)]) is False
    assert unique_people([]) == []


def test_count_in_a_region_counts_feet_not_boxes():
    zone = ZoneSpec(1, "Driveway", RIGHT_HALF, "high", None, None)
    people = [person(50), person(100), person(400)]  # two on the left, one on the right
    assert count_people(people, None, 640, 480).count == 3
    inside = count_people(people, zone, 640, 480)
    assert inside.count == 1 and inside.region == "Driveway"
    assert count_people([], zone, 640, 480).count == 0


def test_a_count_is_marked_approximate_when_it_may_be_low():
    assert count_people([person(100)], None, 640, 480).approximate is False, "one person: nothing is hiding behind anyone"
    assert count_people([], None, 640, 480).approximate is False
    assert count_people(group(2), None, 640, 480).approximate is True, "two well-separated people: a third may still be hidden"
    assert count_people(group(3), None, 640, 480).approximate is True, "measured: overlapping people are missed, so any group is 'at least'"
    assert count_people([person(100), person(140)], None, 640, 480).approximate is True, "overlap"


# ------------------------------------------------------------------ the timer


def test_timer_survives_a_flicker_but_not_a_real_dip_or_a_gap():
    t = CrowdTimer()

    def feed(over: bool, start: float, end: float) -> float:  # detection cycles every half second, like the real thing
        now, elapsed = start, 0.0
        while now <= end:
            elapsed = t.update(over, now, 3.0)
            now += 0.5
        return elapsed

    assert feed(True, 0, 5) == 5.0
    assert feed(False, 5.5, 6.5) == 6.5, "a missed person for a second must not restart the clock"
    assert feed(True, 7, 8) == 8.0
    assert feed(False, 8.5, 12.5) == 0.0, "under the limit for longer than the grace: the episode is over"
    feed(True, 13, 14)
    assert t.update(True, 30.0, 3.0) == 0.0, "no detection cycles for 16 s (no motion, camera outage): treated as gone, restarts"


# ------------------------------------------------------------------ the rule


def test_crowd_alert_after_the_duration_with_an_honest_explanation():
    c = Clock(monitor(threshold=3, seconds=10))
    c.run(9, group(3))
    assert fresh_alerts() == [], "over the limit, but not for long enough yet"
    c.run(2, group(3))
    (alert,) = fresh_alerts()
    d = alert["details"]
    assert alert["type"] == "suspicious_activity" and alert["severity"] == "medium" and d["rule"] == "crowd"
    assert d["people"] == 3 and d["threshold_people"] == 3 and d["threshold_seconds"] == 10 and d["seconds_over"] >= 10
    assert alert["message"].startswith("At least 3 people in view"), alert["message"]
    assert "real number can be higher" in d["note"], "never presented as an exact count"
    assert alert["snapshot"], "has a snapshot"
    c.run(120, group(3))
    assert fresh_alerts() == [], "one alert per crowded episode, however long it lasts"


def test_no_alert_below_the_limit_or_too_briefly():
    c = Clock(monitor(threshold=3, seconds=10))
    c.run(60, group(2))
    assert fresh_alerts() == [], "two people is under the limit of three"
    c.run(6, group(4))
    c.run(30, group(2))
    assert fresh_alerts() == [], "a crowd for 6 s is shorter than the 10 s limit"
    c.run(30, [])
    assert fresh_alerts() == [], "an empty scene"


def test_a_missed_detection_does_not_restart_the_clock_but_a_real_dip_does():
    c = Clock(monitor(threshold=3, seconds=10, crowd_grace_seconds=3.0))
    c.run(6, group(3))
    c.run(1.5, group(2))  # someone missed for three cycles
    c.run(4, group(3))
    assert [a["details"]["rule"] for a in fresh_alerts()] == ["crowd"], "6 + 1.5 + 4 s of crowd, with a short flicker in it"
    c = Clock(monitor(threshold=3, seconds=10, crowd_grace_seconds=3.0))
    c.run(6, group(3))
    c.run(5, group(1))  # genuinely fewer people for 5 s
    c.run(6, group(3))
    assert fresh_alerts() == [], "the earlier 6 s no longer counts after the group really broke up"


def test_cooldown_between_episodes():
    c = Clock(monitor(threshold=3, seconds=5, crowd_alert_cooldown_seconds=60.0))
    c.run(7, group(3))
    assert len(fresh_alerts()) == 1
    c.run(10, [])  # they leave
    c.run(7, group(3))  # a new crowd 17 s later
    assert fresh_alerts() == [], "inside the cooldown: not another alert"
    c.run(10, [])
    c.skip(60)
    c.run(7, group(3))
    assert len(fresh_alerts()) == 1, "after the cooldown a new crowd alerts again"


def test_count_inside_a_zone_only():
    zone = ZoneSpec(1, "Driveway", RIGHT_HALF, "high", None, None)
    c = Clock(monitor(threshold=2, seconds=5, zone_id=1, zones=[zone]))
    c.run(12, [person(50), person(100), person(400)])  # three people, only one in the zone
    assert crowd_alerts(fresh_alerts()) == [], "two people outside the zone do not count towards its limit"
    c.run(8, [person(400), person(480)])
    (alert,) = crowd_alerts(fresh_alerts())
    assert alert["details"]["region"] == "Driveway" and "inside zone 'Driveway'" in alert["message"]


def test_duplicate_boxes_do_not_reach_the_limit():
    tall, shorter_inside = Detection((50, 40, 300, 380), 0.8), Detection((60, 170, 290, 380), 0.6)
    c = Clock(monitor(threshold=3, seconds=5))
    c.run(20, [tall, shorter_inside, person(400)])
    assert fresh_alerts() == [], "two real people drawn with three boxes are still two people"
    assert c.m.status(NOON)["crowd"]["count"] == 2


def test_isolated_extra_detections_do_not_make_a_crowd():
    """One person too many for a single cycle (a person drawn as two, night noise) must not count as a crowd."""
    c = Clock(monitor(threshold=3, seconds=10))
    for _ in range(40):  # two real people; every third cycle the detector adds a third box
        c.run(STEP, group(2))
        c.run(STEP, group(2))
        c.run(STEP, group(3))
    assert fresh_alerts() == [], "a spike on one cycle in three is not three people"
    assert c.m.status(NOON)["crowd"]["count"] == 2
    c = Clock(monitor(threshold=3, seconds=10))
    for _ in range(40):  # three people who are each missed on one cycle in three
        c.run(STEP, group(3))
        c.run(STEP, group(3))
        c.run(STEP, group(2))
    assert len(fresh_alerts()) == 1, "a real group of three that flickers is still a crowd"


def test_rule_off_still_counts_for_the_display():
    c = Clock(monitor(threshold=0))
    c.run(30, group(5))
    assert fresh_alerts() == []
    crowd = c.m.status(NOON)["crowd"]
    assert crowd["count"] == 5 and crowd["threshold"] == 0 and crowd["over"] is False


def test_camera_interruption_ends_the_crowd_episode():
    c = Clock(monitor(threshold=3, seconds=10))
    c.run(8, group(3))
    c.m.interrupt()
    c.skip(1)
    c.run(5, group(3))
    assert fresh_alerts() == [], "8 s + outage + 5 s is not a 13 s crowd"
    assert c.m.status(NOON)["crowd"]["count"] == 3
    c.run(6, group(3))
    assert len(fresh_alerts()) == 1, "a crowd that really lasts 10 s after the outage still alerts"


def test_changing_the_limit_starts_a_fresh_count():
    c = Clock(monitor(threshold=3, seconds=10))
    c.run(8, group(3))
    c.m.set_rules(RulesSpec(crowd_threshold=3, crowd_seconds=10))
    c.run(4, group(3))
    assert fresh_alerts() == [], "saving the rules restarts the timer instead of inheriting it"


def test_only_a_camera_with_a_crowd_limit_looks_at_the_larger_picture():
    """At the normal 320 px input people standing close together are lost (scripts/crowd_benchmark.py), so a camera with a
    crowd limit runs the detector larger; every other camera keeps the fast size."""
    from app.core.config import settings
    from app.services.recording.pipeline import MotionEventPipeline

    class Spy:
        def __init__(self):
            self.calls = []

        def detect(self, frame, confidence=None, **kw):
            self.calls.append(kw)
            return []

    spy = Spy()
    pipeline = MotionEventPipeline("cam1", spy, None)
    pipeline.set_rules(RulesSpec())
    pipeline._detect_people(FRAME)
    pipeline.set_rules(RulesSpec(crowd_threshold=3, crowd_seconds=8))
    pipeline._detect_people(FRAME)
    pipeline.set_rules(RulesSpec(crowd_threshold=0))
    pipeline._detect_people(FRAME)
    assert spy.calls == [{}, {"imgsz": settings.detection.crowd_imgsz}, {}], spy.calls


def test_status_describes_what_is_being_watched():
    zone = ZoneSpec(1, "Driveway", RIGHT_HALF, "high", None, None, loiter_seconds=10)
    m = ActivityMonitor("cam1", ActivityConfig())
    m.set_zones([zone])
    m.set_rules(RulesSpec("23:00", "05:00", True, 4, 15, 1))
    c = Clock(m)
    c.run(2, [person(400), person(50)])
    s = m.status(NOON)
    assert s["zones"] == [{"id": 1, "name": "Driveway", "active": True, "occupied": True}]
    assert s["security_hours"] == {"start": "23:00", "end": "05:00", "active_now": False}
    assert s["fall_check"] is True and s["crowd"]["threshold"] == 4 and s["crowd"]["seconds"] == 15
    assert s["crowd"]["region"] == "Driveway" and s["crowd"]["count"] == 1
    m.clear_live()
    assert m.status(NOON)["zones"][0]["occupied"] is False and m.status(NOON)["crowd"]["count"] == 0


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
    print("crowd counting ok" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
