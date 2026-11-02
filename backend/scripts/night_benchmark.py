"""Repeatable low-light benchmark: the SAME footage at several brightness levels.

For each darkness level it reports what the app really does at night:
  * how the lighting analyser classifies the picture (day / low_light / infrared),
  * how many frames still show a person with each detection strategy:
      raw       YOLO on the dark frame as it is,
      enhanced  YOLO on the gamma + CLAHE copy,
      combined  the app's strategy: try both, keep whichever finds more people,
  * false positives: people "found" in an EMPTY scene at the same darkness,
  * time per frame, so the cost of the extra night work is visible.

"Recall" here is relative to what YOLO finds in the same frames at normal light. There are no
hand-labelled boxes, so it measures how much detection is LOST in the dark, not absolute accuracy.
The footage is a darkened copy of a normal clip plus sensor noise: it is not a real night camera,
and nothing here tests infrared hardware. The infrared row only shows how a synthetic monochrome
clip is classified and detected.

Run from the backend folder:
    python scripts/night_benchmark.py                 # default clip, ~1 minute
    python scripts/night_benchmark.py --frames 40 --json
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.activity.crowd import unique_people  # noqa: E402
from app.services.detection.detector import load_person_detector  # noqa: E402
from app.services.night.lighting import LightingAnalyzer, LowLightEnhancer  # noqa: E402

VIDEOS = Path(__file__).resolve().parent.parent / "sample_videos"
# (exposure relative to the original, sensor-noise sigma added after darkening). 0.12 / 4 is the demo night clip;
# the last rows are deliberately harsh (a phone in a dark room), to find where detection really breaks.
LEVELS = ((1.0, 0.0), (0.5, 4.0), (0.25, 4.0), (0.12, 4.0), (0.06, 4.0), (0.06, 8.0), (0.04, 10.0), (0.03, 12.0))
EMPTY_FRAMES = 6 * 20  # the demo clips start with six seconds of an empty room


def darken(frame: np.ndarray, gain: float, sigma: float, rng) -> np.ndarray:
    if gain >= 1.0:
        return frame
    return np.clip(frame.astype(np.float32) * gain + rng.normal(0, sigma, frame.shape), 0, 255).astype(np.uint8)


def read_frames(path: Path, start: int, count: int, step: int) -> list[np.ndarray]:
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames, index = [], 0
    while len(frames) < count:
        ok, frame = cap.read()
        if not ok:
            break
        if index % step == 0:
            frames.append(frame)
        index += 1
    cap.release()
    return frames


def classify(frame: np.ndarray, config) -> dict:
    """Lighting state after the analyser has settled on this picture (it smooths over a few seconds)."""
    analyzer = LightingAnalyzer(config)
    for _ in range(300):
        state = analyzer.update(frame)
    return state.as_dict()


def run(frames_wanted: int = 60) -> dict:
    cfg = settings.night
    detector = load_person_detector()
    if detector is None:
        raise SystemExit("YOLO is not available (models/yolov8n.pt); run the app once so it can load.")
    enhancer = LowLightEnhancer(cfg)
    clip = VIDEOS / "demo_entrance.mp4"
    if not clip.is_file():
        raise SystemExit("Demo videos are missing. Run:  python scripts/make_demo_videos.py")

    def people(frame, confidence=None):  # exactly what the pipeline does: duplicate boxes round one person are merged
        return unique_people(detector.detect(frame, confidence=confidence))

    action = read_frames(clip, EMPTY_FRAMES, frames_wanted * 4, 4)[:frames_wanted]
    empty = read_frames(clip, 0, 40, 3)
    reference = [len(people(f)) for f in action]
    present = [i for i, n in enumerate(reference) if n > 0]
    rng = np.random.default_rng(7)

    levels = []
    for gain, sigma in LEVELS:
        dark = [darken(f, gain, sigma, rng) for f in action]
        dark_empty = [darken(f, gain, sigma, rng) for f in empty]
        conf = cfg.person_confidence

        raw_counts, enh_counts, comb_counts = [], [], []
        t_enh, t_yolo = [], []
        for f in dark:
            t = time.perf_counter()
            raw = people(f, conf)
            t_yolo.append(time.perf_counter() - t)
            t = time.perf_counter()
            enhanced_frame = enhancer.apply(f)
            t_enh.append(time.perf_counter() - t)
            enh = people(enhanced_frame, conf)
            raw_counts.append(len(raw))
            enh_counts.append(len(enh))
            comb_counts.append(max(len(raw), len(enh)))  # the pipeline keeps the pass that found more people

        fp = {"raw": 0, "enhanced": 0, "combined": 0}
        for f in dark_empty:
            raw, enh = len(people(f, conf)), len(people(enhancer.apply(f), conf))
            fp["raw"] += raw > 0
            fp["enhanced"] += enh > 0
            fp["combined"] += max(raw, enh) > 0

        def recall(counts):
            return sum(1 for i in present if counts[i] > 0) / len(present) if present else float("nan")

        def phantoms(counts):  # frames where MORE distinct people were found than at normal light: possibly invented
            return sum(1 for i, n in enumerate(counts) if n > reference[i])

        levels.append(
            {
                "gain": gain,
                "noise": sigma,
                "lighting": classify(dark[0], cfg),
                "frame_recall": {"raw": recall(raw_counts), "enhanced": recall(enh_counts), "combined": recall(comb_counts)},
                "false_positive_frames": {**fp, "of": len(dark_empty)},
                "phantom_frames": {"raw": phantoms(raw_counts), "enhanced": phantoms(enh_counts), "combined": phantoms(comb_counts), "of": len(dark)},
                "ms_per_frame": {
                    "yolo_pass": round(statistics.median(t_yolo) * 1000, 1),
                    "enhance": round(statistics.median(t_enh) * 1000, 1),
                },
            }
        )

    ir = VIDEOS / "demo_infrared.mp4"
    infrared = None
    if ir.is_file():
        ir_frames = read_frames(ir, EMPTY_FRAMES, 40, 4)
        night_ir = [len(people(f)) for f in ir_frames]
        base = read_frames(VIDEOS / "demo_street.mp4", EMPTY_FRAMES, 40, 4)
        ref_ir = [len(people(f)) for f in base]
        have = [i for i, n in enumerate(ref_ir) if n > 0]
        infrared = {
            "lighting": classify(ir_frames[0], cfg),
            "frame_recall": sum(1 for i in have if night_ir[i] > 0) / len(have) if have else float("nan"),
            "note": "synthetic monochrome clip, not infrared hardware",
        }
    return {"frames_with_a_person_at_normal_light": len(present), "frames_tested": len(action), "levels": levels, "infrared": infrared}


def table(result: dict) -> str:
    out = [
        f"Footage: demo_entrance.mp4, {result['frames_tested']} frames of which {result['frames_with_a_person_at_normal_light']} show a person at normal light (YOLO's own reference).",
        "",
        "| Exposure / noise | Lighting reported | Brightness | Recall raw | Recall enhanced | Recall combined | Frames with more people than at normal light (raw / enh / combined) | Empty-scene false positives (raw / enh / combined) | YOLO ms | Enhance ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for lv in result["levels"]:
        r, fp, ms, li, ph = lv["frame_recall"], lv["false_positive_frames"], lv["ms_per_frame"], lv["lighting"], lv["phantom_frames"]
        out.append(
            f"| {lv['gain']:.2f}x / σ{lv['noise']:g} | {li['kind']} | {li['brightness']:.0f} | {r['raw']:.0%} | {r['enhanced']:.0%} | {r['combined']:.0%} | "
            f"{ph['raw']} / {ph['enhanced']} / {ph['combined']} of {ph['of']} | {fp['raw']} / {fp['enhanced']} / {fp['combined']} of {fp['of']} | {ms['yolo_pass']} | {ms['enhance']} |"
        )
    ir = result["infrared"]
    if ir:
        out += ["", f"Synthetic infrared-style clip: reported as **{ir['lighting']['kind']}** (brightness {ir['lighting']['brightness']:.0f}, colour spread {ir['lighting']['color_spread']:.1f}); person found in {ir['frame_recall']:.0%} of the frames where the normal-light version had one. {ir['note']}."]
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--frames", type=int, default=60, help="frames of footage to test per level (default 60)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args()
    outcome = run(args.frames)
    print(json.dumps(outcome, indent=2) if args.json else table(outcome))
