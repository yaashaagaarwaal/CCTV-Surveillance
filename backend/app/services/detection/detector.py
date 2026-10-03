import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
import torch
from ultralytics import YOLO

from app.core.config import DetectionConfig, settings

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0  # COCO class index for "person"


@dataclass
class Detection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in frame pixels
    confidence: float


class PersonDetector:
    """YOLOv8-based person detector, shared by every camera.

    One model instance serves all camera threads; `detect()` is serialized
    with a lock so two cameras never run MPS/torch inference at the same
    time. Inference takes ~15ms and only runs during active recordings, so
    contention between cameras is negligible.

    Loading the model and running its first inference both pay a one-time
    warmup cost (reading weights off disk, and on Apple Silicon several
    seconds of one-time MPS kernel compilation). Both happen here at
    construction time — not on the first real motion frame — so the live
    stream never stalls waiting for it later.
    """

    def __init__(self, config: DetectionConfig):
        self._confidence_threshold = config.confidence_threshold
        self._imgsz = config.imgsz
        self._lock = threading.Lock()
        self._device = "mps" if torch.backends.mps.is_available() else "cpu"

        config.model_path.parent.mkdir(parents=True, exist_ok=True)
        # YOLO() auto-downloads the weights to this exact path if missing.
        self._model = YOLO(str(config.model_path))

        dummy = np.zeros((self._imgsz, self._imgsz, 3), dtype=np.uint8)
        t0 = time.monotonic()
        self._model.predict(dummy, device=self._device, imgsz=self._imgsz, verbose=False)
        logger.info(
            "YOLO model ready on device=%s (warmup took %.2fs)",
            self._device,
            time.monotonic() - t0,
        )

    def detect(self, frame: np.ndarray, confidence: float | None = None) -> list[Detection]:
        """`confidence` overrides the configured threshold for this call (used at night)."""
        with self._lock:
            results = self._model.predict(
                frame,
                classes=[PERSON_CLASS_ID],
                conf=self._confidence_threshold if confidence is None else confidence,
                imgsz=self._imgsz,
                device=self._device,
                verbose=False,
            )
        detections = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            confidence = float(box.conf[0])
            detections.append(Detection(bbox=(x1, y1, x2, y2), confidence=confidence))
        return detections


def load_person_detector() -> PersonDetector | None:
    """Load the shared detector once at startup; None if disabled or it fails
    (motion detection and recording keep working without it)."""
    if not settings.detection.enabled:
        logger.info("Person detection disabled in settings")
        return None
    try:
        return PersonDetector(settings.detection)
    except Exception:
        logger.exception("Failed to load YOLO model; person detection disabled for all cameras")
        return None
