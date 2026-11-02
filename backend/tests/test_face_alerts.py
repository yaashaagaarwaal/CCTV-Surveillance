"""Unknown-person alerts: when they fire, when they must not, and that every decision explains itself.

Uses a temporary database and synthetic faces; nothing touches real data or cameras.

Covers the part of the alert path where an unknown-person alert is born:
  FaceService._classify (quality gates) -> FaceEventTracker (confirmations, cooldown)
  -> raise_alert() -> SQLite, and the same thing through the real MotionEventPipeline.

Run:  python -m tests.test_face_alerts
"""
import json
import os
import tempfile
import time
from datetime import datetime, timezone

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"

import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import Alert, Camera, Event, FaceObservation  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.detection.detector import Detection  # noqa: E402
from app.services.faces.service import FaceBox, FaceResult, FaceService, Gallery  # noqa: E402
from app.services.faces.storage import resolve  # noqa: E402
from app.services.faces.tracker import FaceEventTracker  # noqa: E402
from app.services.recording.pipeline import MotionEventPipeline  # noqa: E402

FRAME = np.full((480, 640, 3), 110, np.uint8)
CFG = settings.face
CLOCK = {"t": 1000.0}


def face(label, similarity=0.1, reason=None, detail=None, score=0.9):
    result = FaceResult(bbox=(200, 100, 90, 110), score=score, label=label, similarity=similarity, reason=reason)
    if detail is not None:
        result.detail = detail
    return result


def new_event() -> int:
    with SessionLocal() as db:
        event = Event(camera_id="cam1", event_type="person", timestamp=datetime.now(timezone.utc), status="recording")
        db.add(event)
        db.commit()
        return event.id


def clear():
    with SessionLocal() as db:
        for model in (FaceObservation, Alert, Event):
            for row in db.scalars(select(model)):
                db.delete(row)
        db.commit()
    CLOCK["t"] = 1000.0


class fake_clock:
    """time.monotonic() follows CLOCK, so cooldowns can be tested in zero time."""

    def __enter__(self):
        self._real = time.monotonic
        time.monotonic = lambda: CLOCK["t"]

    def __exit__(self, *exc):
        time.monotonic = self._real


def unknown_alerts():
    with SessionLocal() as db:
        return list(db.scalars(select(Alert).where(Alert.type == "unknown_person").order_by(Alert.id)))


def observations(label=None):
    with SessionLocal() as db:
        query = select(FaceObservation).order_by(FaceObservation.id)
        if label:
            query = query.where(FaceObservation.label == label)
        return list(db.scalars(query))


# ---------------------------------------------------------------- classification


def _service():
    svc = FaceService.__new__(FaceService)
    svc.config = CFG
    return svc


def _box(width, nose_offset=0.0):
    row = np.zeros(15, np.float32)
    row[4:6], row[6:8], row[8:10] = (100, 100), (140, 100), (120 + nose_offset * 40, 120)  # eyes 40 px apart
    return FaceBox(10, 10, width, width, 0.9, row)


def test_quality_gates_say_what_they_measured():
    """A 'not sure' must name the gate AND the measured value against its limit."""
    owner = np.zeros(128, np.float32)
    owner[0] = 1
    stranger = np.zeros(128, np.float32)
    stranger[1] = 1
    gallery = Gallery([1], ["Owner"], [owner])
    svc = _service()

    clear_face = svc._classify(_box(100), stranger, gallery, 120.0)
    assert clear_face.label == "unknown" and clear_face.detail and "0.00" in clear_face.detail, clear_face

    cases = [
        (svc._classify(_box(100), stranger, gallery, 31.0), "too dark to judge", ["31", "40"]),
        (svc._classify(_box(41), stranger, gallery, 120.0), "face too small", ["41", "48"]),
        (svc._classify(_box(100, 0.62), stranger, gallery, 120.0), "face turned away", ["0.62", "0.40"]),
    ]
    for result, reason, numbers in cases:
        assert result.label == "uncertain" and result.reason == reason, result
        assert result.detail and all(n in result.detail for n in numbers), (reason, result.detail)

    between = np.zeros(128, np.float32)
    between[0], between[1] = 0.31, 0.95
    between /= np.linalg.norm(between)
    middle = svc._classify(_box(100), between, gallery, 120.0)
    assert middle.label == "uncertain" and middle.reason == "similarity between thresholds" and "0.31" in middle.detail, middle


# ---------------------------------------------------------------- tracker rules


def test_unknown_alert_only_after_three_confirmations():
    clear()
    tracker, event_id = FaceEventTracker("cam1", CFG), new_event()
    with fake_clock():
        for _ in range(CFG.unknown_confirmations - 1):
            tracker.handle([face("unknown")], FRAME, event_id, 1)
        assert unknown_alerts() == [] and observations("unknown") == [], "two sightings must not alert"
        tracker.handle([face("unknown")], FRAME, event_id, 1)
    alerts = unknown_alerts()
    assert len(alerts) == 1 and alerts[0].severity == "high" and alerts[0].event_id == event_id
    assert alerts[0].snapshot_path and resolve(alerts[0].snapshot_path).is_file(), "snapshot saved with the alert"
    assert len(observations("unknown")) == 1
    with SessionLocal() as db:
        assert db.get(Event, event_id).event_type == "unknown_person", "the event is typed unknown_person"


def test_unknown_alert_explains_itself():
    clear()
    tracker, event_id = FaceEventTracker("cam1", CFG), new_event()
    with fake_clock():
        for _ in range(CFG.unknown_confirmations):
            tracker.handle([face("unknown", similarity=0.12, detail="similarity 0.12 is below the unknown limit 0.25")], FRAME, event_id, 1)
    details = json.loads(unknown_alerts()[0].details or "{}")
    assert details.get("rule") == "unknown_person", details
    assert details.get("confirmations") == CFG.unknown_confirmations and details.get("similarity") == 0.12, details
    assert "3" in details.get("explanation", "") and "0.25" in details["explanation"], details


def test_uncertain_faces_never_alert_but_keep_their_reason():
    clear()
    tracker, event_id = FaceEventTracker("cam1", CFG), new_event()
    why = "too dark to judge: brightness 31 (needs 40)"
    with fake_clock():
        for _ in range(30):
            tracker.handle([face("uncertain", 0.06, "too dark to judge", why)], FRAME, event_id, 1)
    assert unknown_alerts() == [] and observations("unknown") == [], "quality-gated faces must never raise an unknown alert"
    seen = observations("uncertain")
    assert len(seen) == 1, "one logged observation per interval, not one per cycle"
    assert seen[0].reason == why, f"the observation must keep why it was uncertain, got {seen[0].reason!r}"


def test_nobody_registered_means_no_unknown_alert():
    clear()
    tracker, event_id = FaceEventTracker("cam1", CFG), new_event()
    with fake_clock():
        for _ in range(10):
            tracker.handle([face("unknown")], FRAME, event_id, 0)
    assert unknown_alerts() == []


def test_unknown_next_to_a_known_person_still_counts():
    clear()
    tracker, event_id = FaceEventTracker("cam1", CFG), new_event()
    owner = FaceResult(bbox=(20, 100, 90, 110), score=0.95, label="known", person_id=1, name="Owner", similarity=0.8)
    with fake_clock():
        for _ in range(CFG.unknown_confirmations):
            tracker.handle([owner, face("unknown")], FRAME, event_id, 1)
    assert len(unknown_alerts()) == 1 and len(observations("known")) == 1


def test_night_needs_more_confirmations():
    clear()
    tracker, event_id = FaceEventTracker("cam1", CFG), new_event()
    needed = max(CFG.unknown_confirmations, settings.night.unknown_confirmations)
    with fake_clock():
        for _ in range(needed - 1):
            tracker.handle([face("unknown")], FRAME, event_id, 1, night=True)
        assert unknown_alerts() == []
        tracker.handle([face("unknown")], FRAME, event_id, 1, night=True)
    assert len(unknown_alerts()) == 1


def test_cooldown_suppresses_repeats_but_not_a_later_visit():
    clear()
    tracker = FaceEventTracker("cam1", CFG)

    def visit():
        event_id = new_event()
        tracker.reset_event()
        for _ in range(CFG.unknown_confirmations):
            tracker.handle([face("unknown")], FRAME, event_id, 1)

    with fake_clock():
        visit()
        CLOCK["t"] += 20
        visit()  # inside the 60 s cooldown: recorded, not alerted
        assert len(unknown_alerts()) == 1 and len(observations("unknown")) == 2
        CLOCK["t"] += CFG.alert_cooldown_seconds + 1
        visit()  # a genuinely later visit alerts again
    assert len(unknown_alerts()) == 2


# ---------------------------------------------------------------- through the real pipeline


class ScriptedDetector:
    def __init__(self, clock):
        self.clock = clock

    def detect(self, frame, confidence=None):
        return [Detection((300, 200, 360, 380), 0.9)] if self.clock["t"] - 5000.0 >= 2.0 else []


class FakeFaces:
    """Stands in for the face models; returns one scripted face per recognition cycle."""

    people_count = 1

    def __init__(self, result):
        self.result, self.cycles = result, 0

    def analyze(self, frame, regions=None, brightness_frame=None):
        self.cycles += 1
        return [self.result]


def run_pipeline(result, seconds=12):
    clock = {"t": 5000.0}
    real = time.monotonic
    time.monotonic = lambda: clock["t"]
    fps = settings.capture_fps
    try:
        faces = FakeFaces(result)
        pipeline = MotionEventPipeline("cam1", ScriptedDetector(clock), faces)
        rng = np.random.default_rng(0)
        for i in range(int((seconds + 2) * fps)):
            frame = np.full((480, 640, 3), 120, np.uint8)
            if clock["t"] - 5000.0 >= 1.5:
                x = (i * 9) % 500
                frame[300:420, x : x + 100] = rng.integers(0, 255, (120, 100, 3), dtype=np.uint8)
            pipeline.process(frame)
            clock["t"] += 1 / fps
        pipeline.close()
    finally:
        time.monotonic = real
    return faces


def test_pipeline_unknown_face_becomes_a_stored_alert():
    clear()
    faces = run_pipeline(face("unknown", 0.07, detail="similarity 0.07 is below the unknown limit 0.25"))
    assert faces.cycles >= CFG.unknown_confirmations, "recognition must run on enough cycles"
    alerts = unknown_alerts()
    assert len(alerts) == 1, f"expected exactly one alert, got {len(alerts)}"
    with SessionLocal() as db:
        event = db.get(Event, alerts[0].event_id)
        assert event is not None and event.event_type == "unknown_person" and event.recording_path


def test_pipeline_poor_quality_face_stays_uncertain_and_says_why():
    clear()
    why = "face turned away: yaw 0.71 (max 0.40)"
    run_pipeline(face("uncertain", 0.06, "face turned away", why))
    assert unknown_alerts() == [], "a turned face must not raise an unknown-person alert"
    seen = observations("uncertain")
    assert seen and seen[0].reason == why, [o.reason for o in seen]


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
    print("face alerts ok" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
