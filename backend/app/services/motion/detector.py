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

    def __init__(self, sensitivity: int, min_area: int, warmup_frames: int):
        self._subtractor = cv2.createBackgroundSubtractorMOG2(
            history=500, varThreshold=sensitivity, detectShadows=True
        )
        self._min_area = min_area
        self._warmup_frames = warmup_frames
        self._frames_seen = 0
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def process(self, frame: np.ndarray) -> bool:
        """Feed one frame in. Returns True if meaningful motion is present."""
        self._frames_seen += 1
        mask = self._subtractor.apply(frame)

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
