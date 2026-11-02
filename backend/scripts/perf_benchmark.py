"""Performance of the live pipeline, measured (simulated camera, real models, temporary database).

  A. Cost of each AI stage per call (YOLO, faces, crowd counting, night enhancement).
  B. The live picture while the AI works: a simulated 30 fps 720p webcam feeds a real CameraWorker. Each frame carries its
     capture number, so "picture age" is the true time between capture and the live JPEG being published. Five loads, from
     YOLO alone up to faces + zone + crowd rule, and a dim clip that triggers night mode. CPU and memory are the whole process.
  C. Alert latency: a staged clip is played in REAL TIME through the file-camera path; the footage itself defines the earliest
     moment each alert could legitimately fire (found with the detector on every frame), and the delay after that is reported.

No real camera is involved. Numbers depend on this machine; the script prints it. Nothing is estimated.

Run from the backend folder (about 4 minutes):
    python scripts/perf_benchmark.py            # tables
    python scripts/perf_benchmark.py --json
"""
import argparse
import collections
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/perf.db"
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import psutil  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.db.models import Alert, Camera  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.activity import monitor as monitor_module  # noqa: E402
from app.services.activity.crowd import count_people, unique_people  # noqa: E402
from app.services.activity.rules import RulesSpec  # noqa: E402
from app.services.activity.zones import ZoneSpec  # noqa: E402
from app.services.camera.base import BaseCamera  # noqa: E402
from app.services.camera.factory import CameraSpec, build_camera  # noqa: E402
from app.services.camera.manager import CameraWorker  # noqa: E402
from app.services.detection.fire import load_fire_detector  # noqa: E402
from app.services.detection.detector import load_person_detector  # noqa: E402
from app.services.faces.service import load_face_service  # noqa: E402
from app.services.night.lighting import LowLightEnhancer  # noqa: E402
from app.services.recording.pipeline import MotionEventPipeline  # noqa: E402

VIDEOS = Path(__file__).resolve().parent.parent / "sample_videos"
W, H, SRC_FPS, BITS = 1280, 720, 30, 20
FULL_FRAME = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
RIGHT_HALF = ((0.5, 0.0), (1.0, 0.0), (1.0, 1.0), (0.5, 1.0))


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))] if values else float("nan")


def machine() -> str:
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip() or platform.processor()
    return f"{chip}, {psutil.cpu_count()} cores, {psutil.virtual_memory().total / 2**30:.0f} GB RAM, {platform.platform()}"


def frames_of(clip: str, start_s: float, count: int, step: int = 2, size=None) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(VIDEOS / clip))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(start_s * 20))
    out, i = [], 0
    while len(out) < count:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            out.append(cv2.resize(frame, size) if size else frame)
        i += 1
    cap.release()
    return out


# ------------------------------------------------------------------------------------------------- A: stage costs
def stage_costs(detector, faces, fire=None) -> dict:
    def timed(fn, frames, repeats=1):
        ts = []
        for frame in frames:
            t = time.perf_counter()
            for _ in range(repeats):
                fn(frame)
            ts.append((time.perf_counter() - t) / repeats * 1000)
        return {"median_ms": round(statistics.median(ts), 2), "p95_ms": round(pct(ts, 0.95), 2), "n": len(ts)}

    crowd = frames_of("demo_crowd.mp4", 20, 40, 2, (W, H))
    close = frames_of("demo_entrance.mp4", 8, 40, 2, (W, H))
    for f in crowd[:3] + close[:3]:  # warm-up
        detector.detect(f)
    boxes = {id(f): detector.detect(f) for f in close}
    people = [detector.detect(f) for f in crowd]
    enhancer = LowLightEnhancer(settings.night)
    out = {
        "YOLO pass, 1280x720, staged crowd (4 people)": timed(detector.detect, crowd),
        "YOLO pass, 1280x720, close-up faces": timed(detector.detect, close),
        "night enhancement (gamma + CLAHE), 1280x720": timed(enhancer.apply, close),
        "duplicate merge + crowd count, 4 people": {
            "median_ms": round(statistics.median([(lambda t0: (count_people(d, None, W, H), (time.perf_counter() - t0) * 1000)[1])(time.perf_counter()) for d in people * 50]), 4),
            "p95_ms": None, "n": len(people) * 50,
        },
    }
    if fire is not None:
        for f in crowd[:3]:
            fire.detect(f)
        out["fire/smoke model pass, 1280x720 (once per camera per second)"] = timed(fire.detect, crowd)
    if faces is not None:
        ts = []
        for f in close:
            regions = [d.bbox for d in boxes[id(f)]]
            t = time.perf_counter()
            faces.analyze(f, regions=regions or None, brightness_frame=f)
            ts.append((time.perf_counter() - t) * 1000)
        out["face detect + recognise, 1280x720, close-up faces"] = {"median_ms": round(statistics.median(ts), 2), "p95_ms": round(pct(ts, 0.95), 2), "n": len(ts)}
    return out


# ------------------------------------------------------------------------------------------------- B: live smoothness
def stamp(frame, seq):
    for i in range(BITS):
        frame[0:16, i * 16 : (i + 1) * 16] = 255 if (seq >> i) & 1 else 0


def read_stamp(frame):
    return sum(1 << i for i in range(BITS) if frame[2:14, i * 16 + 2 : (i + 1) * 16 - 2].mean() > 127)


class SimulatedWebcam(BaseCamera):
    """A driver producing 30 fps on its own clock that keeps only the newest frame, like a laptop camera."""

    def __init__(self, clip: str):
        super().__init__("sim", "sim", 0)
        self.clip, self.captured_at = clip, {}
        self._frame, self._cv, self._stop, self._open = None, threading.Condition(), threading.Event(), False

    def open(self):
        self._video = cv2.VideoCapture(str(VIDEOS / self.clip))
        self._stop.clear()
        self._open = True
        threading.Thread(target=self._produce, daemon=True).start()
        return True

    def _produce(self):
        seq, due = 0, time.monotonic()
        while not self._stop.is_set():
            due += 1 / SRC_FPS
            time.sleep(max(0.0, due - time.monotonic()))
            seq += 1
            ok, f = self._video.read()
            if not ok:
                self._video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, f = self._video.read()
            f = cv2.resize(f, (W, H))
            stamp(f, seq)
            self.captured_at[seq] = time.monotonic()
            with self._cv:
                self._frame = f
                self._cv.notify_all()

    def read(self):
        with self._cv:
            if not self._cv.wait_for(lambda: self._frame is not None, timeout=3):
                return False, None
            f, self._frame = self._frame, None
            return True, f

    def is_opened(self):
        return self._open

    def release(self):
        self._stop.set()
        self._open = False


def live_load(name, clip, detector, faces, rules, zones, seconds, fire=None) -> dict:
    camera = SimulatedWebcam(clip)
    pipeline = MotionEventPipeline("sim", detector, faces, fire)
    pipeline.set_zones(zones)
    pipeline.set_rules(rules)
    cycles, yolo = [], {"n": 0}
    original_analyze = pipeline.analyze
    original_detect = detector.detect if detector is not None else None

    def timed_analyze(frame):
        t = time.perf_counter()
        original_analyze(frame)
        cycles.append((time.perf_counter() - t) * 1000)

    def counted_detect(*a, **k):
        yolo["n"] += 1
        return original_detect(*a, **k)

    pipeline.analyze = timed_analyze
    if detector is not None:
        detector.detect = counted_detect
    worker = CameraWorker(CameraSpec(id="sim", name="sim", type="webcam", source="0"), camera, pipeline)
    process = psutil.Process()
    worker.start()
    try:
        time.sleep(8)  # motion warm-up, recording starts, models running
        cycles.clear()
        yolo["n"] = 0
        process.cpu_percent(None)
        cpu_before = sum(process.cpu_times()[:2])
        ages, shown, last, began = [], 0, None, time.monotonic()
        while time.monotonic() - began < seconds:
            jpg = worker.get_latest_jpeg()
            if jpg is not None and jpg is not last:
                last = jpg
                shown += 1  # every distinct picture the capture thread published
                frame = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
                captured = camera.captured_at.get(read_stamp(frame))  # an overlay drawn over the stamp makes it unreadable: age is then skipped
                if captured:
                    ages.append((time.monotonic() - captured) * 1000)
            time.sleep(0.004)
        elapsed = time.monotonic() - began
        cpu = (sum(process.cpu_times()[:2]) - cpu_before) / elapsed * 100
        rss = process.memory_info().rss / 2**20
        night = pipeline.get_lighting()["night"]
        people = pipeline.get_monitoring()["crowd"]["count"]
    finally:
        worker.stop()
        pipeline.analyze = original_analyze
        if detector is not None:
            detector.detect = original_detect
    return {
        "load": name,
        "live_fps": round(shown / elapsed, 1),
        "picture_age_ms": {"median": round(statistics.median(ages), 1), "p95": round(pct(ages, 0.95), 1), "max": round(max(ages), 1)},
        "ai_cycles_per_s": round(len(cycles) / elapsed, 1),
        "ai_cycle_ms": {"median": round(statistics.median(cycles), 1), "p95": round(pct(cycles, 0.95), 1), "max": round(max(cycles), 1)},
        "yolo_calls_per_s": round(yolo["n"] / elapsed, 1),
        "cpu_percent_of_one_core": round(cpu),
        "rss_mb": round(rss),
        "night_mode": night,
        "people_counted_at_end": people,
    }


# ------------------------------------------------------------------------------------------------- C: alert latency
def reference_times(detector, clip: str, zone: ZoneSpec | None, crowd_limit: int | None, crowd_seconds: int) -> dict:
    """Earliest legitimate alert moments, from the detector run on EVERY frame of the clip (20 fps)."""
    cap = cv2.VideoCapture(str(VIDEOS / clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 20.0
    first_in_zone, over_since, crowd_at, i = None, None, None, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = i / fps
        i += 1
        people = unique_people(detector.detect(frame))
        h, w = frame.shape[:2]
        if zone and first_in_zone is None and any(zone.contains((d.bbox[0] + d.bbox[2]) / 2, d.bbox[3], w, h) for d in people):
            first_in_zone = t
        if crowd_limit:
            if len(people) >= crowd_limit:
                over_since = t if over_since is None else over_since
                if crowd_at is None and t - over_since >= crowd_seconds:
                    crowd_at = t
            elif over_since is not None and t - over_since > 0:
                over_since = None
    return {"first_in_zone": first_in_zone, "crowd_earliest": crowd_at}


def alert_latency(detector, clip: str, rules: RulesSpec, zones: list[ZoneSpec], expected: dict[str, float | None], seconds: float) -> list[dict]:
    with SessionLocal() as db:
        db.query(Alert).delete()
        db.commit()
    stamps: list[tuple[str, float]] = []
    real_raise = monitor_module.raise_alert

    def recording_raise(**kw):
        result = real_raise(**kw)
        stamps.append((kw["details"]["rule"], time.monotonic()))
        return result

    monitor_module.raise_alert = recording_raise
    camera = build_camera(CameraSpec(id="lat", name="lat", type="file", source=clip))
    first_read = {}
    real_read = camera.read

    def timed_read():
        first_read.setdefault("t", time.monotonic())
        return real_read()

    camera.read = timed_read
    pipeline = MotionEventPipeline("lat", detector, None)
    pipeline.set_zones(zones)
    pipeline.set_rules(rules)
    worker = CameraWorker(CameraSpec(id="lat", name="lat", type="file", source=clip), camera, pipeline)
    worker.start()
    try:
        time.sleep(seconds)
    finally:
        worker.stop()
        monitor_module.raise_alert = real_raise
    start = first_read["t"]
    out = []
    for rule, when in stamps:
        earliest = expected.get(rule)
        out.append({
            "clip": clip, "rule": rule, "alert_at_s": round(when - start, 1),
            "earliest_legitimate_s": None if earliest is None else round(earliest, 1),
            "delay_s": None if earliest is None else round(when - start - earliest, 1),
        })
    return out


# ------------------------------------------------------------------------------------------------- main
def run(seconds: float, skip_live: bool) -> dict:
    init_db()
    with SessionLocal() as db:
        db.add_all([Camera(id="sim", name="sim", type="webcam", source="0"), Camera(id="lat", name="lat", type="file", source="x")])
        db.commit()
    detector = load_person_detector()
    faces = load_face_service(settings.face)
    fire = load_fire_detector()
    if detector is None:
        raise SystemExit("YOLO is not available (models/yolov8n.pt).")
    result = {"machine": machine(), "stage_costs": stage_costs(detector, faces, fire)}

    full = ZoneSpec(1, "Whole picture", FULL_FRAME, "high", None, None, loiter_seconds=10)
    right = ZoneSpec(1, "Right half", RIGHT_HALF, "high", None, None, loiter_seconds=10)
    if not skip_live:
        loads = [
            ("baseline: capture + motion + recording, NO AI models", "demo_crowd.mp4", None, None, RulesSpec(), []),
            ("YOLO only, 4 staged people (crowd clip)", "demo_crowd.mp4", detector, None, RulesSpec(), []),
            ("  + zone + crowd rule (limit 3): YOLO at 640 px", "demo_crowd.mp4", detector, None, RulesSpec(crowd_threshold=3, crowd_seconds=8), [right]),
            ("YOLO only, close-up faces (entrance clip)", "demo_entrance.mp4", detector, None, RulesSpec(), []),
            ("  + face recognition", "demo_entrance.mp4", detector, faces, RulesSpec(), []),
            ("  + faces + zone + crowd rule (limit 2)", "demo_entrance.mp4", detector, faces, RulesSpec(crowd_threshold=2, crowd_seconds=10), [full]),
            ("dim clip: night mode, raw + enhanced passes", "demo_lowlight_zone.mp4", detector, None, RulesSpec(), [right]),
        ]
        if fire is not None:  # A/B pairs for the fire/smoke check: same clip, same load, with and without it
            loads += [
                ("empty room: capture + motion, no AI (fire check OFF)", "demo_empty.mp4", None, None, RulesSpec(), []),
                ("empty room: same + fire/smoke check", "demo_empty.mp4", None, None, RulesSpec(), [], fire),
                ("  + faces + fire/smoke check (entrance clip)", "demo_entrance.mp4", detector, faces, RulesSpec(), [], fire),
            ]
        result["live"] = [live_load(n, c, d, f, r, z, seconds, *extra) for n, c, d, f, r, z, *extra in loads]

    latency = []
    for clip, rules, zones, wanted, length in [
        ("demo_zone_entry.mp4", RulesSpec(), [ZoneSpec(1, "Right half", RIGHT_HALF, "high", None, None)], {"zone": True}, 26),
        ("demo_zone_loiter.mp4", RulesSpec(), [right], {"zone": True, "loiter": 10}, 36),
        ("demo_crowd.mp4", RulesSpec(crowd_threshold=3, crowd_seconds=8), [], {"crowd": (3, 8)}, 32),
    ]:
        ref = reference_times(detector, clip, zones[0] if zones else None, 3 if "crowd" in wanted else None, 8)
        expected = {}
        if "zone" in wanted and ref["first_in_zone"] is not None:
            expected["zone_intrusion"] = ref["first_in_zone"]
            if "loiter" in wanted:
                expected["loitering"] = ref["first_in_zone"] + wanted["loiter"]
        if "crowd" in wanted:
            expected["crowd"] = ref["crowd_earliest"]
        latency += alert_latency(detector, clip, rules, zones, expected, length)
    result["alert_latency"] = latency
    return result


def tables(r: dict) -> str:
    out = [f"Machine: {r['machine']}", "", "A. Cost per call (median / p95 ms)", "", "| Stage | median ms | p95 ms | samples |", "|---|---|---|---|"]
    for name, v in r["stage_costs"].items():
        out.append(f"| {name} | {v['median_ms']} | {v['p95_ms'] if v['p95_ms'] is not None else '-'} | {v['n']} |")
    if "live" in r:
        out += ["", "B. Live picture under load (simulated 30 fps 720p webcam, 20 s measured after 8 s warm-up)", "",
                "| Load | live fps | picture age median / p95 / max ms | AI cycles/s | AI cycle median / p95 / max ms | YOLO calls/s | CPU (% of one core) | RSS MB |", "|---|---|---|---|---|---|---|---|"]
        for v in r["live"]:
            a, c = v["picture_age_ms"], v["ai_cycle_ms"]
            out.append(f"| {v['load']} | {v['live_fps']} | {a['median']} / {a['p95']} / {a['max']} | {v['ai_cycles_per_s']} | {c['median']} / {c['p95']} / {c['max']} | {v['yolo_calls_per_s']} | {v['cpu_percent_of_one_core']} | {v['rss_mb']} |")
    out += ["", "C. Alert latency (staged clips played in real time)", "", "| Clip | Alert | Fired at (s into clip) | Earliest it could legitimately fire (s) | Delay (s) |", "|---|---|---|---|---|"]
    for v in r["alert_latency"]:
        out.append(f"| {v['clip']} | {v['rule']} | {v['alert_at_s']} | {v['earliest_legitimate_s']} | {v['delay_s']} |")
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seconds", type=float, default=20, help="measured seconds per live load (default 20)")
    parser.add_argument("--skip-live", action="store_true", help="only stage costs and alert latency")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    outcome = run(args.seconds, args.skip_live)
    print(json.dumps(outcome, indent=2) if args.json else tables(outcome), flush=True)
    os._exit(0)
