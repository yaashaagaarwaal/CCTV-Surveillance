import logging
import time
from dataclasses import dataclass

import numpy as np
import torch
from ultralytics import YOLO

from app.core.config import DetectionConfig

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0  # COCO class index for "person"


@dataclass
class Detection:
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in frame pixels
    confidence: float


class PersonDetector:
    """YOLOv8-based person detector for one camera.

    Loading the model and running its first inference both pay a one-time
    warmup cost (reading weights off disk, and on Apple Silicon several
    seconds of one-time MPS kernel compilation). Both happen here at
    construction time — not on the first real motion frame — so the live
    stream never stalls waiting for it later.
    """

    def __init__(self, config: DetectionConfig):
        self._confidence_threshold = config.confidence_threshold
        self._imgsz = config.imgsz
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

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self._model.predict(
            frame,
            classes=[PERSON_CLASS_ID],
            conf=self._confidence_threshold,
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
