"""Generate demo "camera" videos for testing multiple camera sources.

Each video is ~20s: an empty static scene, then a real photo containing
people panning through the frame (so motion detection triggers and YOLO has
real people to find). "File" cameras loop these forever, so one laptop can
simulate a multi-camera installation.

Two extra clips simulate night conditions (clearly synthetic: a normal clip
darkened with sensor noise, and a monochrome "infrared-style" clip) so night
mode can be tried without waiting for dark.

Six STAGED clips test the surveillance rules with a plain room and cut-out people (real people from
Ultralytics' bus.jpg photo, composited on the empty room, so YOLO really detects them). The restricted zone
for all of them is the RIGHT HALF of the picture (see docs/DEMO.md):
  demo_empty.mp4            nobody there (with a little sensor noise): nothing may happen
  demo_zone_entry.mp4       one person walks in, steps into the zone, stands a few seconds, leaves
  demo_zone_loiter.mp4      one person walks into the zone and stays for ~25 s
  demo_crowd.mp4            four people arrive one after another and stay together for ~15 s
  demo_repeated.mp4         one person enters the zone, leaves, three times (16 s apart)
  demo_lowlight_zone.mp4    the zone-entry clip darkened with noise (simulated low light, not real night)

It also writes demo_person.jpg, a portrait to register on the People page so the
face-recognition demo works without a webcam.

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


# --------------------------------------------------------------------------------------------
# Staged clips: cut-out people walking on the empty room.

SPRITE_HEIGHT = 210  # px in the 640x480 frame
FEET_Y = 445  # where people's feet are: their position on the floor
# The one clean, full-body person in bus.jpg, found by YOLO (x1, y1, x2, y2). The others in that photo are
# partly hidden by the bus, so cut-outs of them are not whole people.
BUS_PERSON = (221, 405, 344, 857)


def person_sprites() -> list[np.ndarray]:
    """Four BGRA cut-outs of that person, varied (flip, size, colours) so a crowd does not look like
    clones. GrabCut with a fixed seed, so the clips are reproducible."""
    cv2.setRNGSeed(0)
    photo = cv2.imread(str(ASSETS / "bus.jpg"))
    x1, y1, x2, y2 = BUS_PERSON
    mx, my = int((x2 - x1) * 0.12), int((y2 - y1) * 0.05)
    cx1, cy1, cx2, cy2 = max(x1 - mx, 0), max(y1 - my, 0), min(x2 + mx, photo.shape[1]), min(y2 + my, photo.shape[0])
    crop = photo[cy1:cy2, cx1:cx2].copy()
    mask = np.zeros(crop.shape[:2], np.uint8)
    cv2.grabCut(crop, mask, (mx, my, x2 - x1, y2 - y1), np.zeros((1, 65)), np.zeros((1, 65)), 6, cv2.GC_INIT_WITH_RECT)
    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(alpha)  # keep only the person, not stray fragments
    alpha = np.where(labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])), 255, 0).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
    ys, xs = np.where(alpha > 128)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    base = np.dstack([crop, alpha])[box[1] : box[3], box[0] : box[2]]

    def variant(sprite, flip, size, channels):
        out = cv2.flip(sprite, 1) if flip else sprite
        out = np.dstack([out[:, :, list(channels)], out[:, :, 3]])
        height = int(SPRITE_HEIGHT * size)
        return cv2.resize(out, (max(int(out.shape[1] * height / out.shape[0]), 20), height), interpolation=cv2.INTER_AREA)

    return [variant(base, False, 1.0, (0, 1, 2)), variant(base, True, 0.93, (2, 1, 0)), variant(base, False, 1.04, (1, 0, 2)), variant(base, True, 0.97, (0, 2, 1))]


class Actor:
    """A person who is on screen between the first and last keyframe (time in s, x of the feet in px),
    moving in straight lines between keyframes, with a little sway and a walking bob."""

    def __init__(self, sprite: np.ndarray, keyframes: list[tuple[float, float]]):
        self.sprite = sprite
        self.keys = keyframes

    def position(self, t: float) -> tuple[float, float] | None:
        if t < self.keys[0][0] or t > self.keys[-1][0]:
            return None
        for (t0, x0), (t1, x1) in zip(self.keys, self.keys[1:]):
            if t0 <= t <= t1:
                x = x0 + (x1 - x0) * ((t - t0) / (t1 - t0) if t1 > t0 else 1.0)
                moving = abs(x1 - x0) > 1
                bob = 4 * abs(math.sin(t * 7.0)) if moving else 0.0
                return x + (0 if moving else 6 * math.sin(t * 1.7)), FEET_Y - bob
        return self.keys[-1][1], FEET_Y


def paste(frame: np.ndarray, sprite: np.ndarray, x: float, feet_y: float) -> None:
    h, w = sprite.shape[:2]
    x0, y0 = int(round(x - w / 2)), int(round(feet_y - h))
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + w, WIDTH), min(y0 + h, HEIGHT)
    if fx0 >= fx1 or fy0 >= fy1:
        return
    part = sprite[fy0 - y0 : fy1 - y0, fx0 - x0 : fx1 - x0]
    alpha = part[:, :, 3:4].astype(np.float32) / 255.0
    region = frame[fy0:fy1, fx0:fx1].astype(np.float32)
    frame[fy0:fy1, fx0:fx1] = (part[:, :, :3] * alpha + region * (1 - alpha)).astype(np.uint8)


def make_staged(name: str, seconds: float, actors: list[Actor], tint=(95, 85, 75), post=None) -> None:
    path = OUT_DIR / name
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (WIDTH, HEIGHT))
    background = empty_scene(tint)
    rng = np.random.default_rng(3)
    for i in range(int(seconds * FPS)):
        t = i / FPS
        frame = background.copy()
        for actor in sorted((a for a in actors if a.position(t)), key=lambda a: a.position(t)[1]):
            x, feet = actor.position(t)
            paste(frame, actor.sprite, x, feet)
        writer.write(post(frame, rng) if post else frame)
    writer.release()
    print(f"wrote {path} ({path.stat().st_size // 1024} KB, {seconds:.0f} s)")


def sensor_noise(frame: np.ndarray, rng) -> np.ndarray:
    return np.clip(frame.astype(np.float32) + rng.normal(0, 1.2, frame.shape), 0, 255).astype(np.uint8)


def dim_room(frame: np.ndarray, rng) -> np.ndarray:
    """A dim room (a fifth of the light) with sensor noise: low light, but not the near-black of demo_night.mp4."""
    return np.clip(frame.astype(np.float32) * 0.2 + rng.normal(0, 4.0, frame.shape), 0, 255).astype(np.uint8)


def make_staged_clips() -> None:
    a, b, c, d = person_sprites()
    entry = [Actor(a, [(4, -40), (9, 300), (11, 470), (17, 470), (21, 720)])]  # in at 4 s, crosses x=320 (the zone) near 9.5 s, out at 21 s
    make_staged("demo_empty.mp4", 20, [], post=sensor_noise)
    make_staged("demo_zone_entry.mp4", 24, entry)
    make_staged("demo_zone_loiter.mp4", 34, [Actor(a, [(4, -40), (8, 470), (31, 470), (33, 720)])])
    make_staged(
        "demo_crowd.mp4", 30,
        [
            Actor(a, [(4, -40), (6, 90), (26, 90), (28, -60)]),
            Actor(b, [(7, 700), (9, 250), (26, 250), (28, 700)]),
            Actor(c, [(10, -40), (12, 400), (26, 400), (28, 700)]),
            Actor(d, [(13, 700), (15, 560), (26, 560), (28, 700)]),
        ],
    )
    cycles, keys = 3, [(4.0, 720.0)]
    for n in range(cycles):
        start = 4.0 + n * 22.0
        keys += [(start + 0.0, 720.0), (start + 3.0, 470.0), (start + 7.0, 470.0), (start + 10.0, 720.0)]
    repeated = [Actor(b, [(k, x) for k, x in keys[1 + 4 * n : 5 + 4 * n]]) for n in range(cycles)]
    make_staged("demo_repeated.mp4", 4 + cycles * 22, repeated)
    make_staged("demo_lowlight_zone.mp4", 24, entry, post=dim_room)


def make_face_photo(name: str = "demo_person.jpg") -> None:
    """A portrait of the larger face in Ultralytics' zidane.jpg, for registering
    a person on the People page. The other man in the demo videos stays
    unregistered, so he is reported as an unknown person. (Coordinates were
    found with the same face detector the app uses.)"""
    image = cv2.imread(str(ASSETS / "zidane.jpg"))
    x, y, w, h = 917, 98, 136, 174
    crop = image[max(y - 100, 0) : y + h + 150, max(x - 130, 0) : x + w + 130]
    path = OUT_DIR / name
    cv2.imwrite(str(path), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)
    try:
        make_video("demo_entrance.mp4", "zidane.jpg", 1100, (0, 130), (95, 85, 75))
        make_video("demo_street.mp4", "bus.jpg", 720, (330, 470), (70, 90, 110))
        make_video("demo_night.mp4", "zidane.jpg", 1100, (0, 130), (95, 85, 75), post=low_light)
        make_video("demo_infrared.mp4", "bus.jpg", 720, (330, 470), (70, 90, 110), post=infrared_look)
        make_staged_clips()
        make_face_photo()
    except Exception as exc:
        sys.exit(f"Could not generate demo videos: {exc}")
