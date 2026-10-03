"""Generate demo "camera" videos for testing multiple camera sources.

Each video is ~20s: an empty static scene, then a real photo containing
people panning through the frame (so motion detection triggers and YOLO has
real people to find). "File" cameras loop these forever, so one laptop can
simulate a multi-camera installation.

Two extra clips simulate night conditions (clearly synthetic: a normal clip
darkened with sensor noise, and a monochrome "infrared-style" clip) so night
mode can be tried without waiting for dark.

Run from the backend folder:
    python scripts/make_demo_videos.py
"""
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics.utils import ASSETS

OUT_DIR = Path(__file__).resolve().parent.parent / "sample_videos"
WIDTH, HEIGHT, FPS = 640, 480, 20
EMPTY_SECONDS, ACTION_SECONDS = 6, 14


def empty_scene(tint: tuple[int, int, int]) -> np.ndarray:
    """A plain, static room-like gradient (no noise, so it reads as 'no motion')."""
    gradient = np.linspace(0.55, 1.0, HEIGHT, dtype=np.float32)[:, None, None]
    scene = np.ones((HEIGHT, WIDTH, 3), dtype=np.float32) * np.array(tint, dtype=np.float32) * gradient
    return scene.astype(np.uint8)


def make_video(name: str, photo: str, scale_width: int, y_range: tuple[int, int], tint, post=None) -> None:
    image = cv2.imread(str(ASSETS / photo))
    scale = scale_width / image.shape[1]
    image = cv2.resize(image, (scale_width, int(image.shape[0] * scale)))
    max_x = image.shape[1] - WIDTH
    max_y = image.shape[0] - HEIGHT
    if max_x < 0 or max_y < 0:
        raise ValueError(f"{photo} scaled to {image.shape[1]}x{image.shape[0]} is smaller than the {WIDTH}x{HEIGHT} frame")

    path = OUT_DIR / name
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
    background = empty_scene(tint)
    rng = np.random.default_rng(1)
    finish = (lambda f: post(f, rng)) if post else (lambda f: f)

    for _ in range(EMPTY_SECONDS * FPS):
        writer.write(finish(background))

    for i in range(ACTION_SECONDS * FPS):
        t = i / (ACTION_SECONDS * FPS)
        x = int(max_x * (0.5 + 0.5 * math.sin(t * 2 * math.pi * 2)))
        y_lo, y_hi = y_range
        y = min(int(y_lo + (y_hi - y_lo) * (0.5 + 0.5 * math.sin(t * 2 * math.pi * 3))), max_y)
        writer.write(finish(image[y : y + HEIGHT, x : x + WIDTH]))

    writer.release()
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


def low_light(frame: np.ndarray, rng) -> np.ndarray:
    """Dark exposure plus sensor noise, like a color camera at night."""
    return np.clip(frame.astype(np.float32) * 0.12 + rng.normal(0, 4.0, frame.shape), 0, 255).astype(np.uint8)


def infrared_look(frame: np.ndarray, rng) -> np.ndarray:
    """Monochrome with a bright centre and grain, like an IR night-vision camera."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    yy, xx = np.mgrid[0:HEIGHT, 0:WIDTH]
    glow = 1.15 - 0.55 * (((xx - WIDTH / 2) / (WIDTH / 2)) ** 2 + ((yy - HEIGHT / 2) / (HEIGHT / 2)) ** 2)
    out = np.clip(gray * glow + rng.normal(0, 5.0, gray.shape), 0, 255).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    try:
        make_video("demo_entrance.mp4", "zidane.jpg", 1100, (0, 130), (95, 85, 75))
        make_video("demo_street.mp4", "bus.jpg", 720, (330, 470), (70, 90, 110))
        make_video("demo_night.mp4", "zidane.jpg", 1100, (0, 130), (95, 85, 75), post=low_light)
        make_video("demo_infrared.mp4", "bus.jpg", 720, (330, 470), (70, 90, 110), post=infrared_look)
    except Exception as exc:
        sys.exit(f"Could not generate demo videos: {exc}")
