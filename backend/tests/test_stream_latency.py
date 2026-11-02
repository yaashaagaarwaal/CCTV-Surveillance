"""The live picture must stay smooth and current while the AI is busy.

A fake camera delivers 30 fps on its own clock and *queues* frames when the reader is
slow (like RTSP/FFmpeg). A fake person detector takes 150 ms per call, like YOLO plus face
recognition on a busy frame. Each frame carries its sequence number as a pixel pattern, so
we can tell how old the picture is by the time it is published as the live JPEG.

The original single-thread loop failed this twice over: it slept between reads (the queue
grew, so the picture fell more than a second behind) and drew the picture only after the
AI finished (every slow cycle froze the video).

Run:  python -m tests.test_stream_latency
"""
import collections
import os
import statistics
import tempfile
import threading
import time

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models import Event  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.camera import manager as manager_module  # noqa: E402
from app.services.camera.base import BaseCamera, CameraStatus  # noqa: E402
from app.services.camera.factory import CameraSpec  # noqa: E402
from app.services.camera.manager import CameraWorker  # noqa: E402
from app.services.detection.detector import Detection  # noqa: E402
from app.services.recording.pipeline import MotionEventPipeline  # noqa: E402

SOURCE_FPS = 30
BITS = 20
SIZE = (640, 480)  # (w, h)


def stamp(frame, seq):
    for i in range(BITS):
        frame[0:16, i * 16:(i + 1) * 16] = 255 if (seq >> i) & 1 else 0


def read_stamp(frame):
    return sum(1 << i for i in range(BITS) if frame[2:14, i * 16 + 2:(i + 1) * 16 - 2].mean() > 127)


class FakeCamera(BaseCamera):
    """Produces frames at SOURCE_FPS; keeps up to 40 unread ones (a queueing driver)."""

    def __init__(self, fail_after: int | None = None):
        super().__init__("lat", "lat", 0)
        self.captured_at: dict[int, float] = {}
        self.fail_after = fail_after
        self.opens = 0
        self._buf: collections.deque = collections.deque(maxlen=40)
        self._cv = threading.Condition()
        self._stop = threading.Event()
        self._open = False

    def open(self):
        self.opens += 1
        self._stop.clear()
        self._open = True
        threading.Thread(target=self._produce, daemon=True).start()
        return True

    def _produce(self):
        seq, due = 0, time.monotonic()
        while not self._stop.is_set():
            due += 1 / SOURCE_FPS
            time.sleep(max(0.0, due - time.monotonic()))
            seq += 1
            frame = np.full((SIZE[1], SIZE[0], 3), 90, np.uint8)
            x = 40 + (seq * 12) % 400  # a big block sweeping across: unmistakable motion
            frame[200:320, x:x + 120] = 235
            stamp(frame, seq)
            self.captured_at[seq] = time.monotonic()
            with self._cv:
                self._buf.append(frame)
                self._cv.notify_all()

    def read(self):
        with self._cv:
            if not self._cv.wait_for(lambda: self._buf, timeout=2):
                return False, None
            frame = self._buf.popleft()
        if self.fail_after is not None and self.opens == 1 and max(self.captured_at) > self.fail_after:
            return False, None  # the camera "unplugs" once, then works again after reopening
        return True, frame

    def is_opened(self):
        return self._open

    def release(self):
        self._stop.set()
        self._open = False
        with self._cv:
            self._buf.clear()


class SlowDetector:
    """Stands in for YOLO: always finds one person, but takes its time."""

    def __init__(self, seconds=0.15):
        self.seconds, self.calls = seconds, 0

    def detect(self, frame, confidence=None):
        self.calls += 1
        time.sleep(self.seconds)
        return [Detection(bbox=(200, 100, 300, 400), confidence=0.9)]


def make_worker(camera):
    detector = SlowDetector()
    pipeline = MotionEventPipeline("lat", detector, None)
    return CameraWorker(CameraSpec(id="lat", name="lat", type="webcam", source="0"), camera, pipeline), detector, pipeline


def observe(worker, camera, settle, seconds):
    """Watch the published live picture: (fps shown, ages in ms)."""
    ages, last = [], None
    measure_from = time.monotonic() + settle
    until = measure_from + seconds
    while time.monotonic() < until:
        jpg = worker.get_latest_jpeg()
        if jpg is not None and jpg is not last:
            last = jpg
            if time.monotonic() >= measure_from:
                frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                captured = camera.captured_at.get(read_stamp(frame))
                if captured:
                    ages.append((time.monotonic() - captured) * 1000)
        time.sleep(0.003)
    return len(ages) / seconds, sorted(ages)


def test_live_picture_stays_current_while_ai_is_busy():
    camera = FakeCamera()
    worker, detector, pipeline = make_worker(camera)
    worker.start()
    try:
        fps, ages = observe(worker, camera, settle=5, seconds=8)  # settle: motion warm-up, then recording + detection
        p95 = ages[int(0.95 * len(ages))]
        assert detector.calls >= 5, f"the AI must keep running during the test, it ran {detector.calls} times"
        assert fps >= 24, f"live picture shows only {fps:.1f} fps from a 30 fps camera"
        assert p95 <= 120, f"live picture is {p95:.0f} ms old at p95 (median {statistics.median(ages):.0f} ms)"
    finally:
        worker.stop()


def test_analysis_still_detects_and_records():
    camera = FakeCamera()
    worker, detector, pipeline = make_worker(camera)
    worker.start()
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (pipeline.is_recording and pipeline.get_live_detections()):
            time.sleep(0.1)
        assert pipeline.is_recording, "motion should have started a recording"
        assert pipeline.get_live_detections(), "a person should have been detected"
        # The box is a 1 px line and JPEG blurs it, so look for its blue edge (raw background is 90; the line reads ~175).
        # The published picture can be a frame older than the detection, so allow it a moment to catch up.
        drawn = False
        for _ in range(100):
            shown = cv2.imdecode(np.frombuffer(worker.get_latest_jpeg(), np.uint8), cv2.IMREAD_COLOR)
            if shown[100, 205:295, 0].mean() > 140:
                drawn = True
                break
            time.sleep(0.03)
        assert drawn, "the person box should be drawn on the live picture"
    finally:
        worker.stop()
    with SessionLocal() as db:
        events = db.scalars(select(Event).where(Event.camera_id == "lat")).all()
    assert events and all(e.status != "recording" for e in events), "stop() must finalize the recording"


def test_unplugged_camera_goes_offline_then_recovers():
    original_retry = manager_module.RETRY_INTERVAL_SECONDS
    manager_module.RETRY_INTERVAL_SECONDS = 0.3
    camera = FakeCamera(fail_after=SOURCE_FPS * 6)  # about six seconds in
    worker, detector, pipeline = make_worker(camera)
    worker.start()
    try:
        seen = set()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            seen.add(worker.get_status())
            if CameraStatus.OFFLINE in seen and camera.opens >= 2 and worker.get_status() == CameraStatus.ONLINE:
                break
            time.sleep(0.05)
        assert CameraStatus.OFFLINE in seen, "the dropped camera should be reported offline"
        assert camera.opens >= 2 and worker.get_status() == CameraStatus.ONLINE, "and come back by itself"
    finally:
        worker.stop()
        manager_module.RETRY_INTERVAL_SECONDS = original_retry
    with SessionLocal() as db:
        statuses = {e.status for e in db.scalars(select(Event).where(Event.camera_id == "lat"))}
    assert "interrupted" in statuses, f"the recording cut by the outage should be marked interrupted, got {statuses}"
    assert "recording" not in statuses


def main() -> int:
    init_db()
    failures = 0
    for name, func in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        try:
            func()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print("live stream stays smooth" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
