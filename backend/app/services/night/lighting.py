import logging
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.config import NightConfig

logger = logging.getLogger(__name__)

ANALYSIS_SIZE = (64, 48)  # frames are shrunk to this before measuring: ~0.1 ms


@dataclass(frozen=True)
class LightingState:
    night: bool = False
    kind: str = "day"  # "day" | "low_light" | "infrared"
    brightness: float = 128.0  # smoothed mean gray level, 0-255
    color_spread: float = 40.0  # smoothed mean (max - min) color channel, 0-255

    def as_dict(self) -> dict:
        return {
            "night": self.night,
            "kind": self.kind,
            "brightness": round(self.brightness, 1),
            "color_spread": round(self.color_spread, 1),
        }


class LightingAnalyzer:
    """Decides whether a camera is currently in night conditions.

    Two independent signals, both smoothed with an exponential moving average
    so a passing shadow or a flash doesn't flip the mode:
      * low light: brightness falls below `enter_brightness` (and only returns
        to day above the higher `exit_brightness` — hysteresis);
      * infrared: a reasonably bright picture with almost no color. IR
        night-vision feeds are monochrome and often brightly lit, so
        brightness alone would miss them. (A genuinely black-and-white camera
        will therefore always read as "infrared".) Color spread is the average
        gap between a pixel's strongest and weakest channel: unlike HSV
        saturation it isn't inflated by codec noise on near-black pixels.
    """

    def __init__(self, config: NightConfig):
        self.config = config
        self._brightness: float | None = None
        self._color_spread: float | None = None
        self._low_light = False
        self.state = LightingState()

    def update(self, frame: np.ndarray) -> LightingState:
        cfg = self.config
        if not cfg.enabled:
            return self.state

        small = cv2.resize(frame, ANALYSIS_SIZE, interpolation=cv2.INTER_AREA)
        brightness = float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).mean())
        spread = float((small.max(axis=2).astype(np.int16) - small.min(axis=2)).mean())

        if self._brightness is None:  # first frame: start from the measurement itself
            self._brightness, self._color_spread = brightness, spread
        else:
            a = cfg.smoothing
            self._brightness += a * (brightness - self._brightness)
            self._color_spread += a * (spread - self._color_spread)

        if self._low_light:
            self._low_light = self._brightness < cfg.exit_brightness
        else:
            self._low_light = self._brightness < cfg.enter_brightness
        infrared = self._color_spread < cfg.infrared_color_spread and self._brightness >= cfg.infrared_min_brightness

        kind = "infrared" if infrared else "low_light" if self._low_light else "day"
        new_state = LightingState(kind != "day", kind, self._brightness, self._color_spread)
        if new_state.kind != self.state.kind:
            logger.info("Lighting changed: %s -> %s (brightness %.0f, color spread %.0f)", self.state.kind, kind, self._brightness, self._color_spread)
        self.state = new_state
        return new_state


class LowLightEnhancer:
    """Gamma + CLAHE contrast enhancement for dark frames.

    This only re-maps detail the sensor actually captured: it makes dim
    structure easier for a detector to see, but it cannot create information
    that darkness removed, and it amplifies noise along with signal. It is
    applied to the copy of the frame given to the detectors; recordings and
    (by default) the live view stay untouched.
    """

    def __init__(self, config: NightConfig):
        # cv2 CLAHE objects aren't thread-safe, so each camera pipeline owns one.
        self._clahe = cv2.createCLAHE(clipLimit=config.clahe_clip_limit, tileGridSize=(8, 8))
        gamma = max(config.gamma, 0.1)
        self._gamma_lut = np.array([((i / 255.0) ** (1.0 / gamma)) * 255 for i in range(256)], dtype=np.uint8)

    def apply(self, frame: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        lightness, a, b = cv2.split(lab)
        lightness = self._clahe.apply(cv2.LUT(lightness, self._gamma_lut))
        return cv2.cvtColor(cv2.merge((lightness, a, b)), cv2.COLOR_LAB2BGR)
