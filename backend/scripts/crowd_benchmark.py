"""How accurate is the crowd count? Frames where the true number of people is known BECAUSE WE BUILT THEM.

People (the cut-out figures used by the staged demo clips) are placed in a row, 1 to 8 of them, with neighbours overlapping by
0 %, 25 %, 50 % or 75 % of their width, then the real detector and the app's duplicate merge count them. For every setting it
reports how often the count is exactly right, the average count, and how often it is too low or too high, with and without
the duplicate merge.

This is the easy case (clean cut-outs on a plain room, standing figures, no clothing variety). Real crowds are harder, so read the
numbers as an upper bound on accuracy. They are also the honest answer to "how much does overlap hurt a standard detector?".

Run from the backend folder (about 20 s):
    python scripts/crowd_benchmark.py            # table
    python scripts/crowd_benchmark.py --json
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import make_demo_videos as staged  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.activity.crowd import unique_people  # noqa: E402
from app.services.detection.detector import load_person_detector  # noqa: E402

PEOPLE = (1, 2, 3, 4, 6, 8)
OVERLAPS = (0.0, 0.25, 0.5, 0.75)
FRAMES_PER_SETTING = 8


def build_frame(sprites, count: int, overlap: float, rng) -> np.ndarray | None:
    """`count` people in a row, neighbours overlapping by `overlap` of a figure's width. None if they do not fit."""
    frame = staged.empty_scene((95, 85, 75))
    chosen = [sprites[int(rng.integers(len(sprites)))] for _ in range(count)]
    widths = [s.shape[1] for s in chosen]
    step = float(np.mean(widths)) * (1.0 - overlap)
    total = step * (count - 1) + widths[-1]
    if total > staged.WIDTH - 20:
        return None
    x = (staged.WIDTH - total) / 2 + widths[0] / 2 + float(rng.uniform(-6, 6))
    for i, sprite in enumerate(chosen):
        depth = float(rng.uniform(-14, 6))  # people are not all at the same distance: a few pixels of difference in feet position
        staged.paste(frame, sprite, x + i * step + float(rng.uniform(-3, 3)), staged.FEET_Y + depth)
    noise = rng.normal(0, 1.2, frame.shape)
    return np.clip(frame.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def run() -> list[dict]:
    detector = load_person_detector()
    if detector is None:
        raise SystemExit("YOLO is not available (models/yolov8n.pt).")
    sprites = staged.person_sprites()
    rng = np.random.default_rng(11)
    rows = []
    for count in PEOPLE:
        for overlap in OVERLAPS:
            frames = []
            for _ in range(FRAMES_PER_SETTING):
                frame = build_frame(sprites, count, overlap, rng)
                if frame is None:
                    break
                frames.append(frame)
            if not frames:
                continue
            sizes = {}
            for label, size in (("default", None), ("crowd", settings.detection.crowd_imgsz)):  # None = the app's normal input size
                found = [detector.detect(f, imgsz=size) for f in frames]
                sizes[label] = ([len(d) for d in found], [len(unique_people(d)) for d in found])

            def stats(counts):
                return {
                    "exact": sum(c == count for c in counts) / len(counts),
                    "mean": statistics.mean(counts),
                    "too_low": sum(c < count for c in counts) / len(counts),
                    "too_high": sum(c > count for c in counts) / len(counts),
                }

            rows.append({
                "people": count, "overlap": overlap, "frames": len(frames),
                "default": {"raw": stats(sizes["default"][0]), "merged": stats(sizes["default"][1])},
                "crowd": {"raw": stats(sizes["crowd"][0]), "merged": stats(sizes["crowd"][1])},
            })
    return rows


def table(rows: list[dict]) -> str:
    out = [
        f"Known counts (built frames), real YOLOv8n. 'default' = the app's normal input size ({settings.detection.imgsz} px), 'crowd' = the size used on a camera with a crowd limit ({settings.detection.crowd_imgsz} px).",
        "All counts below are after the app's duplicate-box merge unless marked raw.",
        "",
        "| True people | Neighbour overlap | Frames | Exactly right: default / crowd | Mean count: default / crowd | Too low: default / crowd | Too high: crowd (raw / merged) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        d, c = r["default"]["merged"], r["crowd"]["merged"]
        out.append(
            f"| {r['people']} | {r['overlap']:.0%} | {r['frames']} | {d['exact']:.0%} / {c['exact']:.0%} | {d['mean']:.1f} / {c['mean']:.1f} | {d['too_low']:.0%} / {c['too_low']:.0%} | {r['crowd']['raw']['too_high']:.0%} / {c['too_high']:.0%} |"
        )
    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = run()
    print(json.dumps(result, indent=2) if args.json else table(result))
