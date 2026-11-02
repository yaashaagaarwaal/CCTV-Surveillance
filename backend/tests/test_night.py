"""Night mode: classification, hysteresis, enhancement, and what it really does for detection.

Part 1 feeds synthetic pictures to the lighting analyser and the enhancer (no models).
Part 2 runs scripts/night_benchmark.py: the SAME footage at falling brightness with the real YOLO
model, and asserts the properties the README claims. The footage is a darkened copy of a normal clip
plus noise, not a real night camera; "recall" is relative to what YOLO finds at normal light.

Run:  python -m tests.test_night
"""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from app.core.config import settings  # noqa: E402
from app.services.night.lighting import LightingAnalyzer, LowLightEnhancer  # noqa: E402

CFG = settings.night


def grey(level: int) -> np.ndarray:
    return np.full((120, 160, 3), level, np.uint8)


def colour(level: int) -> np.ndarray:
    frame = np.full((120, 160, 3), level, np.uint8)
    frame[:, :, 2] = min(255, level + 60)  # red clearly stronger than blue: a real colour spread
    return frame


def settle(analyzer: LightingAnalyzer, frame: np.ndarray, cycles: int = 400):
    state = None
    for _ in range(cycles):
        state = analyzer.update(frame)
    return state


# ---------------------------------------------------------------- classification


def test_day_low_light_and_infrared_are_told_apart():
    assert settle(LightingAnalyzer(CFG), colour(120)).kind == "day"
    assert settle(LightingAnalyzer(CFG), colour(15)).kind == "low_light"
    infrared = settle(LightingAnalyzer(CFG), grey(100))
    assert infrared.kind == "infrared" and infrared.night and infrared.color_spread < CFG.infrared_color_spread
    assert settle(LightingAnalyzer(CFG), grey(8)).kind == "low_light", "a dark monochrome picture is too dark to be infrared (needs brightness)"
    assert settle(LightingAnalyzer(CFG), colour(120)).night is False


def test_brightness_and_colour_spread_are_measured_correctly():
    state = settle(LightingAnalyzer(CFG), colour(100))
    assert abs(state.brightness - np.mean(0.299 * 160 + 0.587 * 100 + 0.114 * 100)) < 3, state
    assert abs(state.color_spread - 60) < 1, "spread = strongest minus weakest channel"


def test_hysteresis_stops_flicker_between_day_and_night():
    """Night starts below 55 and only ends above 75: in between the previous mode is kept."""
    between = colour(46)  # brightness 64: above the entry level (55), below the exit level (75)
    assert 55 < settle(LightingAnalyzer(CFG), between).brightness < 75
    night_first = LightingAnalyzer(CFG)
    settle(night_first, colour(15))
    assert settle(night_first, between).night is True, "coming from night, a brightness between the two levels stays night"
    day_first = LightingAnalyzer(CFG)
    settle(day_first, colour(120))
    assert settle(day_first, between).night is False, "the very same picture coming from day stays day"
    assert settle(night_first, colour(120)).night is False, "clearly bright again: back to day"


def test_a_flash_or_shadow_does_not_flip_the_mode():
    analyzer = LightingAnalyzer(CFG)
    settle(analyzer, colour(120))
    states = [analyzer.update(colour(5)) for _ in range(8)]  # ~0.4 s of darkness at 20 fps (a passing shadow)
    assert all(not s.night for s in states), "smoothing: eight dark frames are not night"
    analyzer = LightingAnalyzer(CFG)
    settle(analyzer, colour(120))
    for _ in range(120):  # six seconds of real darkness
        state = analyzer.update(colour(5))
    assert state.night, "sustained darkness is"


# ---------------------------------------------------------------- enhancement


def test_enhancer_brightens_without_touching_the_original_and_is_cheap():
    enhancer = LowLightEnhancer(CFG)
    rng = np.random.default_rng(0)
    dark = np.clip(rng.normal(14, 4, (480, 640, 3)), 0, 255).astype(np.uint8)
    before = dark.copy()
    out = enhancer.apply(dark)
    assert out.shape == dark.shape and out.dtype == np.uint8
    assert np.array_equal(dark, before), "recordings use the raw frame: enhancement must work on a copy"
    assert out.mean() > dark.mean() + 20, "a dark picture comes out clearly brighter"
    began = time.perf_counter()
    for _ in range(20):
        enhancer.apply(dark)
    per_frame_ms = (time.perf_counter() - began) / 20 * 1000
    assert per_frame_ms < 15, f"enhancement took {per_frame_ms:.1f} ms per 640x480 frame"


# ---------------------------------------------------------------- detection on the same footage


def test_enhancement_helps_where_it_matters_and_never_hurts():
    import night_benchmark

    result = night_benchmark.run(60)
    levels = {(lv["gain"], lv["noise"]): lv for lv in result["levels"]}
    assert result["frames_with_a_person_at_normal_light"] >= 50, "the reference footage must actually contain people"
    for key, lv in levels.items():
        r = lv["frame_recall"]
        assert r["combined"] >= r["raw"] - 1e-9, f"the combined strategy must never find fewer frames than raw at {key}: {r}"
        assert lv["false_positive_frames"]["combined"] == 0, f"no person may appear in an empty dark room at {key}"
        assert lv["ms_per_frame"]["enhance"] < 15
        assert lv["phantom_frames"]["combined"] <= 0.15 * lv["phantom_frames"]["of"], f"too often more people than at normal light at {key}"
    for key in ((0.5, 4.0), (0.25, 4.0), (0.12, 4.0)):
        assert levels[key]["frame_recall"]["combined"] >= 0.95, f"a moderately dark clip must still be detected: {key}"
        assert levels[key]["lighting"]["night"] is True, f"{key} should be classified as night"
    hard = levels[(0.06, 8.0)]["frame_recall"]
    assert hard["combined"] > hard["raw"] + 0.10, f"in very dark noisy footage enhancement should add at least ten points: {hard}"
    assert levels[(0.03, 12.0)]["frame_recall"]["combined"] < 0.5, "near-black footage is beyond what enhancement can recover: do not claim otherwise"
    ir = result["infrared"]
    assert ir["lighting"]["kind"] == "infrared" and ir["frame_recall"] >= 0.9, ir


def main() -> int:
    failures = 0
    for name, func in sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)):
        began = time.time()
        try:
            func()
            print(f"PASS  {name}  ({time.time() - began:.0f} s)", flush=True)
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            failures += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}", flush=True)
    print("night mode behaves" if not failures else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
