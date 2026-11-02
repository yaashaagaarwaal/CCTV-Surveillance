"""Try the fire/smoke model on a photo or a video file, without starting the server or touching any database.

For every checked frame it prints what the model saw, then says what the app's alert rules would have done with it
(confirmation needs several checks in a few seconds, so one lucky frame is not an alert). Use it to see how the model reacts to
YOUR footage, for example a video of a candle flame, a campfire or smoke played on your phone, or a photo.

Run from the backend folder:
    python scripts/fire_check.py path/to/clip.mp4            # every 1 s of video
    python scripts/fire_check.py photo.jpg --save marked.jpg   # one picture; writes the picture with the boxes drawn
    python scripts/fire_check.py clip.mp4 --every 0.5 --fire-conf 0.4 --smoke-conf 0.5   # try other thresholds

Never start a real fire or smoke to test this. Play a video on a screen instead.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

# The alert rules import the database layer; point it at a throwaway file so this script can never touch real data.
_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/unused.db")
os.environ.setdefault("STORAGE_DIR", f"{_tmp}/storage")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services.activity.fire import FireMonitor, draw_boxes  # noqa: E402
from app.services.detection.fire import FireSmokeDetector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", type=Path, help="a video file or a picture")
    parser.add_argument("--every", type=float, default=settings.fire.interval_seconds, help="seconds between checks (default: the app's interval)")
    parser.add_argument("--fire-conf", type=float, default=settings.fire.fire_confidence)
    parser.add_argument("--smoke-conf", type=float, default=settings.fire.smoke_confidence)
    parser.add_argument("--save", type=Path, help="write the most convincing frame, with its boxes, to this picture")
    args = parser.parse_args()

    if not args.path.is_file():
        print(f"No such file: {args.path}")
        return 2
    config = settings.fire.model_copy(update={"fire_confidence": args.fire_conf, "smoke_confidence": args.smoke_conf})
    try:
        detector = FireSmokeDetector(config)
    except FileNotFoundError as exc:
        print(f"{exc}\nSee README, 'Fire and smoke detection', for where to get the weights.")
        return 2

    frames: list[tuple[float, object]] = []
    image = cv2.imread(str(args.path))
    if image is not None:
        frames = [(0.0, image)]
    else:
        cap = cv2.VideoCapture(str(args.path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, round(fps * args.every))
        index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if index % step == 0:
                frames.append((index / fps, frame))
            index += 1
        if not frames:
            print("Could not read any frames from that file.")
            return 2

    monitor = FireMonitor("check", config)
    best = (0.0, None, None)
    alerts = []
    counts = {"fire": 0, "smoke": 0}
    top = {"fire": 0.0, "smoke": 0.0}
    for t, frame in frames:
        found = detector.detect(frame)
        for d in found:
            counts[d.kind] += 1
            top[d.kind] = max(top[d.kind], d.confidence)
        shown = ", ".join(f"{d.kind} {d.confidence:.0%}" for d in found) or "-"
        print(f"t={t:7.1f}s  {shown}")
        for c in monitor.update(found, t):
            alerts.append((t, c))
        score = max((d.confidence for d in found), default=0.0)
        if score > best[0]:
            best = (score, frame.copy(), found)

    print(f"\nChecked {len(frames)} frame(s). Seen: fire in {counts['fire']} (best {top['fire']:.0%}), smoke in {counts['smoke']} (best {top['smoke']:.0%}).")
    needs = f"{config.fire_confirm_hits} checks for fire, {config.smoke_confirm_hits} for smoke, within {config.confirm_window_seconds:.0f} s"
    if alerts:
        for t, c in alerts:
            print(f"The app WOULD raise a {c.kind.upper()} alert at t={t:.1f}s ({c.hits} checks, best {c.confidence:.0%}).")
    else:
        print(f"The app would NOT raise an alert (it needs {needs}; thresholds fire {args.fire_conf}, smoke {args.smoke_conf}).")
    if args.save and best[1] is not None:
        draw_boxes(best[1], best[2])
        cv2.imwrite(str(args.save), best[1])
        print(f"Wrote {args.save}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
