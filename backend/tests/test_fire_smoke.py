"""Fire and smoke detection: confirmation rules, thresholds, cooldowns, stored alerts, and that it never slows the live picture.

Temporary database and mocked model output (a fake YOLO that returns scripted boxes), so no fire footage, camera or model file is needed.
The last group runs the REAL model on staged footage (a negative check: there is no fire in it) and is skipped if the weights are absent.

  FireMonitor (pure rules, fake clock)  ->  FireSmokeDetector (mocked model: per-class thresholds, classes by name)
  ->  MotionEventPipeline -> raise_alert() -> SQLite + snapshot + event

Run:  python -m tests.test_fire_smoke
"""
import os
import stat
import tempfile
import threading
import time
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.services.detection.fire as fire_module  # noqa: E402
from app.core.config import FireConfig, settings  # noqa: E402
from app.db.models import Alert, Camera, Event  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.activity.fire import FireMonitor  # noqa: E402
from app.services.alerts import ALERT_TYPES, serialize_alert  # noqa: E402
from app.services.detection.fire import FireDetection, FireSmokeDetector, load_fire_detector  # noqa: E402
from app.services.faces.storage import resolve  # noqa: E402
from app.services.recording.pipeline import MotionEventPipeline  # noqa: E402

CFG = settings.fire
SMOKE, FIRE = 0, 1  # the model's own class ids (D-Fire order); the code must not depend on them
BOX = (40, 30, 180, 150)
FRAME = np.full((240, 320, 3), 120, np.uint8)
CLOCK = {"t": 1000.0}


# ------------------------------------------------------------------ a fake YOLO


class _Num:
    def __init__(self, value):
        self.value = value

    def __getitem__(self, i):
        return self

    def __float__(self):
        return float(self.value)

    def __int__(self):
        return int(self.value)

    def tolist(self):
        return list(self.value)


class _Box:
    def __init__(self, cls_id, confidence, bbox):
        self.cls, self.conf, self.xyxy = _Num(cls_id), _Num(confidence), _Num(bbox)


class FakeModel:
    """Returns the boxes in `self.boxes` (class id, confidence, bbox), honouring `conf` like Ultralytics does."""

    def __init__(self, names):
        self.names = names
        self.boxes: list[tuple[int, float, tuple]] = []
        self.calls = 0
        self.delay = 0.0
        self.fail = False

    def predict(self, frame, conf=0.25, **_):
        self.calls += 1
        if self.fail:
            raise RuntimeError("model blew up")
        if self.delay:
            time.sleep(self.delay)

        class Result:
            pass

        result = Result()
        result.boxes = [_Box(c, p, b) for c, p, b in self.boxes if p >= conf]
        return [result]


def make_detector(names=None, config=None):
    """The real FireSmokeDetector, constructed normally, with YOLO replaced by a FakeModel (and a stand-in weights file)."""
    weights = Path(_tmp) / "fake_fire.pt"
    weights.write_bytes(b"not a real model")
    model = FakeModel(names or {SMOKE: "smoke", FIRE: "fire"})
    real = fire_module.YOLO
    fire_module.YOLO = lambda path: model
    try:
        detector = FireSmokeDetector((config or CFG).model_copy(update={"model_path": weights}))
    finally:
        fire_module.YOLO = real
    model.calls = 0  # the warm-up pass does not count
    return detector, model


# ------------------------------------------------------------------ helpers


def clear():
    with SessionLocal() as db:
        for model in (Alert, Event):
            for row in db.scalars(select(model)):
                db.delete(row)
        db.commit()
    CLOCK["t"] = 1000.0


def alerts(kind=None):
    with SessionLocal() as db:
        query = select(Alert).order_by(Alert.id)
        if kind:
            query = query.where(Alert.type == kind)
        return list(db.scalars(query))


def seen(kind, confidence=0.9):
    return [FireDetection(kind, BOX, confidence)]


class fake_clock:
    """time.monotonic() follows CLOCK so cooldowns run in zero time."""

    def __enter__(self):
        self._real = time.monotonic
        time.monotonic = lambda: CLOCK["t"]

    def __exit__(self, *exc):
        time.monotonic = self._real


def run_pipeline(schedule, seconds, fire_detector, fps=20):
    """Feed `seconds` of an unchanging picture (no motion, nobody in it). `schedule(t)` -> model boxes at second t."""
    pipeline = MotionEventPipeline("cam1", None, None, fire_detector)
    with fake_clock():
        for _ in range(int(seconds * fps)):
            t = CLOCK["t"] - 1000.0
            yield_boxes = schedule(t)
            fire_detector._model.boxes = yield_boxes
            pipeline.process(FRAME.copy())
            CLOCK["t"] += 1 / fps
        pipeline.close()
    return pipeline


# ------------------------------------------------------------------ the rules (no model, no clock)


def test_one_frame_never_alerts_and_repeated_sightings_do():
    monitor = FireMonitor("cam1", CFG)
    assert monitor.update(seen("fire"), 0.0) == [], "a single sighting must not alert"
    assert monitor.update(seen("fire"), 1.0) == []
    confirmed = monitor.update(seen("fire"), 2.0)
    assert [c.kind for c in confirmed] == ["fire"] and confirmed[0].hits == CFG.fire_confirm_hits and confirmed[0].confidence == 0.9


def test_nothing_seen_nothing_raised():
    monitor = FireMonitor("cam1", CFG)
    assert all(monitor.update([], t) == [] for t in range(60))
    assert monitor.status(60.0)["fire"] == {"seen": False, "hits": 0, "needed": CFG.fire_confirm_hits, "active": False, "confidence": None}


def test_fire_and_smoke_are_judged_separately():
    monitor = FireMonitor("cam1", CFG)
    out = [c.kind for t in range(CFG.fire_confirm_hits) for c in monitor.update(seen("fire"), float(t))]
    assert out == ["fire"], "fire alone confirms fire only"
    assert monitor.status(3.0)["smoke"]["hits"] == 0, "fire sightings never count towards smoke"

    monitor = FireMonitor("cam1", CFG)
    out = [(t, c.kind) for t in range(CFG.smoke_confirm_hits) for c in monitor.update(seen("smoke"), float(t))]
    assert out == [(CFG.smoke_confirm_hits - 1, "smoke")], "smoke needs its own, larger number of sightings"

    both = FireMonitor("cam1", CFG)
    kinds = sorted(c.kind for t in range(CFG.smoke_confirm_hits) for c in both.update(seen("fire") + seen("smoke"), float(t)))
    assert kinds == ["fire", "smoke"], "when both are there, each gets its own alert"


def test_sightings_spread_too_far_apart_never_confirm():
    monitor = FireMonitor("cam1", CFG)
    gap = CFG.confirm_window_seconds / (CFG.fire_confirm_hits - 1) + 0.5  # the first one has expired before the third arrives
    assert all(monitor.update(seen("fire"), i * gap) == [] for i in range(10)), "flickers spread over a long time are not a fire"


def test_one_alert_per_episode_even_if_it_burns_for_minutes():
    monitor = FireMonitor("cam1", CFG)
    raised = [c for t in range(300) for c in monitor.update(seen("fire"), float(t))]
    assert len(raised) == 1, f"{len(raised)} alerts for one continuous fire"


def test_a_new_episode_inside_the_cooldown_is_held_back_then_released():
    monitor = FireMonitor("cam1", CFG)
    first = [c for t in range(5) for c in monitor.update(seen("fire"), float(t))]
    assert len(first) == 1
    gone = CFG.clear_seconds + 5
    again_at = 4 + gone  # back well inside the cooldown
    assert again_at < CFG.fire_alert_cooldown_seconds
    inside = [c for i in range(8) for c in monitor.update(seen("fire"), again_at + i)]
    assert inside == [], "inside the cooldown a new episode must not alert"
    # ... it is still burning when the cooldown ends, so it is raised then (held back, not lost)
    released = []
    t = again_at + 8
    while t < CFG.fire_alert_cooldown_seconds + 30 and not released:
        released = monitor.update(seen("fire"), t)
        t += 1
    first_alert_at = CFG.fire_confirm_hits - 1  # sightings at t = 0, 1, 2
    assert len(released) == 1 and t - 1 == first_alert_at + CFG.fire_alert_cooldown_seconds, f"released at {t - 1}"


def test_losing_the_camera_ends_the_episode():
    monitor = FireMonitor("cam1", CFG)
    for t in range(CFG.fire_confirm_hits - 1):
        assert monitor.update(seen("fire"), float(t)) == []
    monitor.interrupt()  # camera dropped: those sightings are not combined with anything seen after the gap
    assert monitor.update(seen("fire"), float(CFG.fire_confirm_hits)) == []
    assert monitor.status(float(CFG.fire_confirm_hits))["fire"]["hits"] == 1


# ------------------------------------------------------------------ the detector (mocked model)


def test_each_class_has_its_own_confidence_threshold():
    detector, model = make_detector()
    low, ok = 0.1, 0.99
    just_under_fire, just_over_fire = CFG.fire_confidence - 0.01, CFG.fire_confidence + 0.01
    just_under_smoke, just_over_smoke = CFG.smoke_confidence - 0.01, CFG.smoke_confidence + 0.01
    assert CFG.smoke_confidence != CFG.fire_confidence, "the two classes are tuned separately"

    model.boxes = [(FIRE, low, BOX), (SMOKE, low, BOX)]
    assert detector.detect(FRAME) == []
    model.boxes = [(FIRE, just_under_fire, BOX), (SMOKE, just_under_smoke, BOX)]
    assert detector.detect(FRAME) == [], "just under each threshold is ignored"
    model.boxes = [(FIRE, just_over_fire, BOX), (SMOKE, just_over_smoke, BOX)]
    found = detector.detect(FRAME)
    assert sorted(d.kind for d in found) == ["fire", "smoke"]
    # a confidence between the two thresholds is kept only for the class whose limit is lower (fire, by default)
    between = (CFG.fire_confidence + CFG.smoke_confidence) / 2
    model.boxes = [(FIRE, between, BOX), (SMOKE, between, BOX)]
    assert [d.kind for d in detector.detect(FRAME)] == ["fire"]
    model.boxes = [(FIRE, ok, BOX)]
    assert detector.detect(FRAME)[0].bbox == BOX


def test_classes_are_found_by_name_not_by_position():
    detector, model = make_detector(names={0: "fire", 1: "smoke"})  # the opposite order to the model we ship
    model.boxes = [(0, 0.95, BOX)]
    assert [d.kind for d in detector.detect(FRAME)] == ["fire"]
    model.boxes = [(1, 0.95, BOX)]
    assert [d.kind for d in detector.detect(FRAME)] == ["smoke"]
    model.boxes = [(7, 0.95, BOX)]  # a class that is neither
    assert detector.detect(FRAME) == []


def test_a_model_without_both_classes_is_refused_and_missing_weights_switch_the_feature_off():
    try:
        make_detector(names={0: "person", 1: "car"})
    except ValueError as exc:
        assert "fire" in str(exc) and "smoke" in str(exc)
    else:
        raise AssertionError("a model that cannot tell fire from smoke must be refused")

    original = settings.fire
    settings.fire = original.model_copy(update={"model_path": Path(_tmp) / "no_such_file.pt"})
    try:
        assert load_fire_detector() is None, "missing weights must disable the feature, not crash start-up"
        settings.fire = original.model_copy(update={"enabled": False})
        assert load_fire_detector() is None
    finally:
        settings.fire = original


# ------------------------------------------------------------------ through the real pipeline, to the database


def test_fire_becomes_a_stored_alert_with_evidence():
    clear()
    detector, _ = make_detector()
    run_pipeline(lambda t: [(FIRE, 0.82, BOX)] if 2 <= t < 9 else [], 12, detector)
    stored = alerts()
    assert [a.type for a in stored] == ["fire"], [a.type for a in stored]
    alert = stored[0]
    assert alert.camera_id == "cam1" and alert.severity == "critical" and alert.created_at is not None
    payload = serialize_alert(alert, event_available=True)
    assert payload["details"]["rule"] == "fire" and payload["details"]["confidence"] == 0.82
    assert payload["details"]["confirmations"] >= CFG.fire_confirm_hits and "explanation" in payload["details"]
    assert payload["has_snapshot"], "the alert must carry its snapshot"
    snapshot = resolve(alert.snapshot_path)
    assert stat.S_IMODE(snapshot.stat().st_mode) == 0o600, "snapshots are private"
    picture = cv2.imread(str(snapshot))
    assert picture is not None and picture.shape[:2] == FRAME.shape[:2]
    x1, y1, x2, y2 = BOX
    assert not np.array_equal(picture[y1 - 2 : y1 + 3, x1:x2], FRAME[y1 - 2 : y1 + 3, x1:x2]), "the box is drawn on the snapshot"
    with SessionLocal() as db:
        event = db.get(Event, alert.event_id)
        assert event is not None and event.event_type == "fire" and event.recording_path and event.max_confidence == 0.82, "a clip is recorded even though nothing moved"
        assert resolve(event.recording_path).is_file()
        from app.api.events import _reasons_summary  # the Events page explains why an event was flagged

        why = _reasons_summary(db, [event.id])[event.id]
        assert [(r["type"], r["rule"]) for r in why] == [("fire", "fire")], why


def test_smoke_becomes_its_own_alert_type():
    clear()
    detector, _ = make_detector()
    run_pipeline(lambda t: [(SMOKE, 0.77, BOX)] if 1 <= t < 12 else [], 15, detector)
    stored = alerts()
    assert [(a.type, a.severity) for a in stored] == [("smoke", "high")], [(a.type, a.severity) for a in stored]
    with SessionLocal() as db:
        assert db.get(Event, stored[0].event_id).event_type == "smoke"


def test_no_detection_means_no_alert_and_no_recording():
    clear()
    detector, model = make_detector()
    run_pipeline(lambda t: [], 20, detector)
    assert alerts() == []
    with SessionLocal() as db:
        assert list(db.scalars(select(Event))) == [], "an idle camera with nothing detected records nothing"
    assert model.calls >= 15, "it was still looking (about once a second)"


def test_confidence_below_the_threshold_never_alerts():
    clear()
    detector, _ = make_detector()
    run_pipeline(lambda t: [(FIRE, CFG.fire_confidence - 0.05, BOX), (SMOKE, CFG.smoke_confidence - 0.05, BOX)], 30, detector)
    assert alerts() == [], "a steady but unconvincing detection is not an alert"


def test_a_brief_flicker_does_not_alert():
    clear()
    detector, _ = make_detector()
    run_pipeline(lambda t: [(FIRE, 0.95, BOX)] if 3 <= t < 4.2 else [], 20, detector)  # about one or two checks
    assert alerts() == []


def test_cooldown_through_the_pipeline():
    clear()
    detector, _ = make_detector()
    def schedule(t):
        for a, b in ((2, 8), (30, 40)):  # second visit starts 22 s after the first ended: inside the 120 s cooldown
            if a <= t < b:
                return [(FIRE, 0.9, BOX)]
        return [(FIRE, 0.9, BOX)] if 140 <= t < 150 else []

    run_pipeline(schedule, 160, detector)
    stored = alerts("fire")
    assert len(stored) == 2, f"expected the first and the one after the cooldown, got {len(stored)}"


def test_the_model_is_asked_about_once_a_second_not_every_frame():
    detector, model = make_detector()
    pipeline = MotionEventPipeline("cam1", None, None, detector)
    start = time.monotonic()
    for _ in range(60):
        pipeline.analyze(FRAME.copy())
    elapsed = time.monotonic() - start
    assert elapsed < CFG.interval_seconds * 0.9, "the test itself must finish inside one interval"
    assert model.calls == 1, f"60 frames inside one interval must cost one model pass, not {model.calls}"


def test_a_slow_model_never_delays_the_live_picture():
    """The model runs on the analysis thread; render() (the capture thread's job) must not wait for it."""
    detector, model = make_detector()
    model.delay = 0.5
    pipeline = MotionEventPipeline("cam1", None, None, detector)
    worker = threading.Thread(target=pipeline.analyze, args=(FRAME.copy(),))
    worker.start()
    time.sleep(0.05)  # the slow pass is now running
    slowest = 0.0
    while worker.is_alive():
        t0 = time.perf_counter()
        pipeline.render(FRAME)
        slowest = max(slowest, time.perf_counter() - t0)
    worker.join()
    assert model.calls == 1
    assert slowest < 0.05, f"render() took {slowest * 1000:.0f} ms while the model was busy"


def test_a_failing_model_is_contained():
    clear()
    detector, model = make_detector()
    model.fail = True
    pipeline = MotionEventPipeline("cam1", None, None, detector)
    with fake_clock():
        for _ in range(100):
            pipeline.process(FRAME.copy())  # must not raise
            CLOCK["t"] += 0.1
        model.fail = False
        model.boxes = [(FIRE, 0.9, BOX)]
        for _ in range(100):
            pipeline.process(FRAME.copy())
            CLOCK["t"] += 0.1
    assert len(alerts("fire")) == 1, "after the model recovers, detection works again"


def test_detections_are_drawn_on_the_live_picture_but_never_on_the_raw_frame():
    detector, model = make_detector()
    model.boxes = [(FIRE, 0.9, BOX)]
    pipeline = MotionEventPipeline("cam1", None, None, detector)
    raw = FRAME.copy()
    pipeline.analyze(raw)
    shown = pipeline.render(raw)
    assert np.array_equal(raw, FRAME), "the raw frame (what is recorded) is never modified"
    assert shown is not raw and not np.array_equal(shown, FRAME), "the live copy shows the box"
    assert pipeline.get_monitoring()["fire"]["fire"]["seen"] is True


def test_fire_detection_off_changes_nothing():
    pipeline = MotionEventPipeline("cam1", None, None, None)
    assert pipeline.get_monitoring()["fire"] is None
    assert pipeline.render(FRAME) is FRAME, "no overlay work when the feature is off"
    pipeline.process(FRAME.copy())
    pipeline.close()


def test_the_alert_type_is_known_everywhere_it_must_be():
    assert "fire" in ALERT_TYPES and "smoke" in ALERT_TYPES
    from app.services.notifications.email import TYPE_TITLES
    from app.services.recording.event_types import EVENT_TYPE_RANK

    assert "fire" in TYPE_TITLES and "smoke" in TYPE_TITLES
    assert EVENT_TYPE_RANK["fire"] > EVENT_TYPE_RANK["smoke"] > EVENT_TYPE_RANK["restricted_area"], "a fire outranks everything else an event can be"


# ------------------------------------------------------------------ the real model (negative checks on staged footage)

REAL_WEIGHTS = CFG.model_path.is_file()
VIDEOS = Path(__file__).resolve().parent.parent / "sample_videos"


def _real_or_skip(*videos):
    if not REAL_WEIGHTS:
        raise Skip(f"no fire/smoke weights at {CFG.model_path}")
    for video in videos:
        if not (VIDEOS / video).is_file():
            raise Skip(f"{video} missing (run scripts/make_demo_videos.py)")


class Skip(Exception):
    pass


def _every_frame(video, limit=None):
    cap = cv2.VideoCapture(str(VIDEOS / video))
    frames = []
    while len(frames) < (limit or 10**9):
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    return frames


def test_real_model_loads_and_names_its_classes():
    _real_or_skip()
    detector = load_fire_detector()
    assert detector is not None
    assert sorted(detector._kind_of.values()) == ["fire", "smoke"]


def test_real_model_finds_nothing_in_rooms_with_people_in_them():
    _real_or_skip("demo_empty.mp4", "demo_zone_loiter.mp4", "demo_crowd.mp4", "demo_night.mp4")
    detector = load_fire_detector()
    for video in ("demo_empty.mp4", "demo_zone_loiter.mp4", "demo_crowd.mp4", "demo_night.mp4"):
        frames = _every_frame(video)[::10]
        found = [d for frame in frames for d in detector.detect(frame)]
        assert found == [], f"{video}: {[(d.kind, round(d.confidence, 2)) for d in found][:3]}"


def test_real_model_blurry_grey_background_does_not_become_a_smoke_alert():
    """demo_entrance.mp4 (out-of-focus TV footage) made the first draft of these thresholds raise a false smoke alert."""
    _real_or_skip("demo_entrance.mp4")
    detector = load_fire_detector()
    per_frame = [detector.detect(frame) for frame in _every_frame("demo_entrance.mp4")]
    monitor = FireMonitor("cam1", CFG)
    raised = []
    for loop in range(3):  # a file camera repeats
        for i in range(0, len(per_frame), int(settings.capture_fps * CFG.interval_seconds)):
            raised += monitor.update(per_frame[i], (loop * len(per_frame) + i) / settings.capture_fps)
    assert raised == [], f"false alert(s): {[(c.kind, c.confidence) for c in raised]}"


# ------------------------------------------------------------------ runner


def main() -> int:
    init_db()
    with SessionLocal() as db:
        db.add(Camera(id="cam1", name="Test cam", type="file", source="x"))
        db.commit()
    failures = skipped = 0
    for name, func in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        try:
            func()
            print(f"PASS  {name}")
        except Skip as why:
            skipped += 1
            print(f"SKIP  {name}: {why}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"fire/smoke ok ({skipped} skipped)" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
