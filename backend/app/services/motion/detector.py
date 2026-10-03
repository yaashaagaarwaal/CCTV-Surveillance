import cv2
import numpy as np


class MotionDetector:
    """Background-subtraction motion detector for one camera.

    Uses MOG2 rather than naive frame-differencing because it builds an
    adaptive model of the "empty scene" and keeps updating it, so slow
    changes (sunlight moving, auto-exposure/white-balance drift) get folded
    into the background instead of being flagged as motion — the single
    biggest source of false positives for an indoor/outdoor home camera.
    """

    def __init__(self, sensitivity: int, min_area: int, warmup_frames: int, lighting_jump_threshold: float = 30.0):
        self._sensitivity = sensitivity
        self._subtractor = self._new_subtractor()
        self._jump_threshold = lighting_jump_threshold
        self._reference_level: float | None = None
        self._min_area = min_area
        self._warmup_frames = warmup_frames
        self._frames_seen = 0
        self._settle_frames = 0
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def _new_subtractor(self):
        return cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=self._sensitivity, detectShadows=True)

    def _lighting_jumped(self, frame: np.ndarray) -> bool:
        """Did the average brightness change abruptly (a lighting event, not movement)?"""
        level = float(frame[::8, ::8].mean())
        if self._reference_level is None:
            self._reference_level = level
        jumped = abs(level - self._reference_level) > self._jump_threshold
        self._reference_level += 0.2 * (level - self._reference_level)  # follows gradual change closely
        return jumped

    def notify_lighting_change(self, frames: int = 40) -> None:
        """Switching between day and night changes the picture's noise level
        abruptly; ignore motion for a couple of seconds while the background
        model re-learns it, instead of treating the switch as movement."""
        self._settle_frames = frames

    def process(self, frame: np.ndarray, denoise: bool = False) -> bool:
        """Feed one frame in. Returns True if meaningful motion is present.
        `denoise` blurs slightly first — dark frames are grainy, and grain
        looks like motion to background subtraction."""
        self._frames_seen += 1
        if self._lighting_jumped(frame):
            # Relearn the scene from scratch rather than treat the whole frame as movement.
            self._subtractor = self._new_subtractor()
            self._frames_seen = 1
        if denoise:
            frame = cv2.GaussianBlur(frame, (5, 5), 0)
        mask = self._subtractor.apply(frame)

        if self._settle_frames > 0:
            self._settle_frames -= 1
            return False

        if self._frames_seen <= self._warmup_frames:
            # Background model is still learning the empty scene — every
            # pixel looks like foreground on frame 1, so don't react yet.
            return False

        # MOG2 marks shadow pixels as gray (127); threshold above that so
        # shadows cast by real motion don't count as motion themselves.
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        # Open (erode+dilate) clears single-pixel sensor noise; dilate then
        # regrows real blobs so a moving object isn't split into fragments
        # each too small to pass the area check.
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._kernel, iterations=2)
        mask = cv2.dilate(mask, self._kernel, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return any(cv2.contourArea(c) >= self._min_area for c in contours)
