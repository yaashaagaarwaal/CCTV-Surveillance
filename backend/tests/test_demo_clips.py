"""The staged demo clips through the REAL pipeline (motion -> recording -> YOLO -> rules -> alerts).

Each clip is played at 20 fps on a fake clock (so a 70 s clip takes seconds), with the real YOLO model,
a throwaway database, and the restricted zone set to the right half of the picture, exactly as
docs/DEMO.md describes. It checks what should happen AND what must not:

  demo_empty            nothing: no event, no alert, count 0
  demo_zone_entry       exactly one zone-intrusion alert, no loitering, no repeat
  demo_zone_loiter      intrusion, then one loitering alert after the configured time
  demo_crowd            one crowd alert at a limit of 3; NO alert at a limit of 5 (more than there are
                        people: duplicate boxes must not make up the difference)
  demo_repeated         intrusion once (cooldown) and a repeated-entry alert on the third visit
  demo_lowlight_zone    the same single intrusion in a dim room, found in night mode

Footage is staged (cut-out people on a plain room), so this proves the rules work on real detector output
for those scenes. It does not prove the same on a real camera. Needs the clips and models:
    python scripts/make_demo_videos.py

Run:  python -m tests.test_demo_clips
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"

import cv2  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import Alert, Camera, Event  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.activity.rules import RulesSpec  # noqa: E402
from app.services.activity.zones import ZoneSpec  # noqa: E402
from app.services.detection.detector import load_person_detector  # noqa: E402
from app.services.recording.pipeline import MotionEventPipeline  # noqa: E402

VIDEOS = Path(__file__).resolve().parent.parent / "sample_videos"
RIGHT_HALF = ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0))
DETECTOR = None


def zone(**kw) -> ZoneSpec:
    base = dict(id=1, name="Right half", points=RIGHT_HALF, severity="high", schedule_start=None, schedule_end=None,
                loiter_seconds=0, repeat_entries=0, repeat_window_seconds=300)
    return ZoneSpec(**{**base, **kw})


def play(clip: str, zones=(), rules=RulesSpec(), loops: int = 1) -> dict:
    """Run a clip through the pipeline. Returns alerts, events and what the tile would have shown."""
    with SessionLocal() as db:
        for model in (Alert, Event):
            db.execute(delete(model))
        db.commit()
    clock = {"t": 5000.0}
    real = time.monotonic
    time.monotonic = lambda: clock["t"]
    seen = {"peak_count": 0, "night": False, "approximate": False}
    try:
        pipeline = MotionEventPipeline("cam1", DETECTOR, None)
        pipeline.set_zones(list(zones))
        pipeline.set_rules(rules)
        fps = settings.capture_fps
        for _ in range(loops):  # a file camera loops forever; each pass starts straight after the last
            cap = cv2.VideoCapture(str(VIDEOS / clip))
            step = max(1, round(cap.get(cv2.CAP_PROP_FPS) / fps))
            index = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                index += 1
                if index % step:
                    continue
                pipeline.analyze(frame)
                status = pipeline.get_monitoring()["crowd"]
                seen["peak_count"] = max(seen["peak_count"], status["count"])
                seen["approximate"] |= status["approximate"]
                seen["night"] |= pipeline.get_lighting()["night"]
                clock["t"] += 1 / fps
        pipeline.close()
    finally:
        time.monotonic = real
    with SessionLocal() as db:
        alerts = [{"type": a.type, "severity": a.severity, "details": json.loads(a.details), "message": a.message} for a in db.scalars(select(Alert).order_by(Alert.id))]
        events = [e.event_type for e in db.scalars(select(Event).order_by(Event.id))]
    return {"alerts": alerts, "rules": [a["details"]["rule"] for a in alerts], "events": events, **seen}


def test_empty_scene_does_nothing():
    run = play("demo_empty.mp4", [zone(loiter_seconds=5, repeat_entries=2)], RulesSpec(crowd_threshold=2))
    assert run["alerts"] == [] and run["events"] == [], run
    assert run["peak_count"] == 0


def test_one_person_entering_the_zone_alerts_once():
    run = play("demo_zone_entry.mp4", [zone()])
    assert run["rules"] == ["zone_intrusion"], run["rules"]
    alert = run["alerts"][0]
    assert alert["type"] == "restricted_area" and alert["severity"] == "high" and "Right half" in alert["message"]
    assert run["events"] == ["restricted_area"], "the recording is flagged with the alert"


def test_a_person_staying_in_the_zone_is_flagged_as_loitering():
    run = play("demo_zone_loiter.mp4", [zone(loiter_seconds=10)])
    assert run["rules"] == ["zone_intrusion", "loitering"], run["rules"]
    loiter = run["alerts"][1]["details"]
    assert loiter["threshold_seconds"] == 10 and 10 <= loiter["dwell_seconds"] <= 16, loiter
    short = play("demo_zone_loiter.mp4", [zone(loiter_seconds=60)])
    assert short["rules"] == ["zone_intrusion"], "a 60 s limit is longer than the 25 s stay: negative case"


def test_a_crowd_alerts_at_three_but_never_at_five_people():
    run = play("demo_crowd.mp4", rules=RulesSpec(crowd_threshold=3, crowd_seconds=8))
    assert run["rules"] == ["crowd"], run["rules"]
    details = run["alerts"][0]["details"]
    assert 3 <= details["people"] <= 4 and details["threshold_people"] == 3 and details["seconds_over"] >= 8, details
    assert run["alerts"][0]["message"].startswith("At least"), "a lower bound, never an exact count"
    assert 3 <= run["peak_count"] <= 4, f"four people were staged; saw up to {run['peak_count']}"
    above = play("demo_crowd.mp4", rules=RulesSpec(crowd_threshold=5, crowd_seconds=3))
    assert above["alerts"] == [], f"only four people are there: a limit of five must not fire (peak {above['peak_count']})"


def test_leaving_and_coming_back_three_times():
    run = play("demo_repeated.mp4", [zone(repeat_entries=3, repeat_window_seconds=300)])
    assert run["rules"] == ["zone_intrusion", "repeated_entry"], run["rules"]
    repeated = run["alerts"][1]
    assert repeated["details"]["entries"] == 3 and repeated["severity"] == "critical", repeated
    two = play("demo_repeated.mp4", [zone(repeat_entries=4, repeat_window_seconds=300)])
    assert two["rules"] == ["zone_intrusion"], "three visits do not reach a limit of four: negative case"


def test_a_person_who_arrives_during_the_cooldown_and_stands_still_is_still_watched():
    """Found by the soak test: the clip loops, and on the second pass the person walks in while the previous recording's
    10 s cooldown is still running, then stands still. A still person makes no motion, so nothing started a recording and
    the camera never looked at them: no intrusion, no loitering, for the whole 25 s stay."""
    activity = settings.activity
    saved = activity.suspicious_alert_cooldown_seconds, activity.zone_alert_cooldown_seconds
    activity.suspicious_alert_cooldown_seconds = activity.zone_alert_cooldown_seconds = 1.0  # so alerts are not hidden by their own cooldowns
    try:
        run = play("demo_zone_loiter.mp4", [zone(loiter_seconds=10)], loops=2)
    finally:
        activity.suspicious_alert_cooldown_seconds, activity.zone_alert_cooldown_seconds = saved
    assert run["rules"].count("zone_intrusion") == 2, run["rules"]
    assert run["rules"].count("loitering") == 2, f"the second visit must be caught loitering too: {run['rules']}"


def test_low_light_footage_still_finds_the_intruder():
    run = play("demo_lowlight_zone.mp4", [zone()])
    assert run["night"], "the dim room should have been classified as low light / night"
    assert run["rules"] == ["zone_intrusion"], run["rules"]


def main() -> int:
    global DETECTOR
    needed = ["demo_empty", "demo_zone_entry", "demo_zone_loiter", "demo_crowd", "demo_repeated", "demo_lowlight_zone"]
    if not all((VIDEOS / f"{n}.mp4").is_file() for n in needed):
        print("Staged demo clips are missing. Run:  python scripts/make_demo_videos.py")
        return 2
    DETECTOR = load_person_detector()
    if DETECTOR is None:
        print("YOLO is not available (models/yolov8n.pt).")
        return 2
    init_db()
    with SessionLocal() as db:
        db.add(Camera(id="cam1", name="Test cam", type="file", source="x"))
        db.commit()
    failures = 0
    for name, func in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        began = time.time()
        try:
            func()
            print(f"PASS  {name}  ({time.time() - began:.0f} s)", flush=True)
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}", flush=True)
    print("demo clips behave" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
