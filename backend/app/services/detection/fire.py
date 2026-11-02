import logging
import time
from dataclasses import dataclass

import numpy as np
import torch
from ultralytics import YOLO

from app.core.config import FireConfig, settings
from app.services.detection.detector import INFERENCE_LOCK

logger = logging.getLogger(__name__)

KINDS = ("fire", "smoke")


@dataclass
class FireDetection:
    kind: str  # "fire" | "smoke"
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2 in frame pixels
    confidence: float


class FireSmokeDetector:
    """YOLOv8 fire/smoke detector, shared by every camera (same pattern as PersonDetector).

    The class ids are read from the model's own `names`, never assumed, so a different fire model works as long as it
    names its classes "fire" and "smoke". A model without both is refused at start-up. The weights are loaded from
    `FIRE__MODEL_PATH`; nothing is downloaded automatically.
    """

    def __init__(self, config: FireConfig):
        self._config = config
        self._device = "mps" if torch.backends.mps.is_available() else "cpu"
        if not config.model_path.is_file():
            raise FileNotFoundError(f"fire/smoke weights not found at {config.model_path}")
        self._model = YOLO(str(config.model_path))
        by_name = {str(name).lower(): int(index) for index, name in self._model.names.items()}
        missing = [kind for kind in KINDS if kind not in by_name]
        if missing:
            raise ValueError(f"model classes are {sorted(by_name)}; it must name both 'fire' and 'smoke' (missing {missing})")
        self._kind_of = {by_name[kind]: kind for kind in KINDS}
        self._minimum = {"fire": config.fire_confidence, "smoke": config.smoke_confidence}

        dummy = np.zeros((config.imgsz, config.imgsz, 3), dtype=np.uint8)
        t0 = time.monotonic()
        self._model.predict(dummy, device=self._device, imgsz=config.imgsz, verbose=False)
        logger.info("Fire/smoke model ready on device=%s (warmup %.2fs), classes %s", self._device, time.monotonic() - t0, sorted(by_name))

    def detect(self, frame: np.ndarray) -> list[FireDetection]:
        """Fire and smoke boxes at or above each class's own confidence."""
        with INFERENCE_LOCK:
            results = self._model.predict(
                frame,
                conf=min(self._minimum.values()),
                imgsz=self._config.imgsz,
                device=self._device,
                verbose=False,
            )
        found = []
        for box in results[0].boxes:
            kind = self._kind_of.get(int(box.cls[0]))
            confidence = float(box.conf[0])
            if kind is None or confidence < self._minimum[kind]:
                continue
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            found.append(FireDetection(kind=kind, bbox=(x1, y1, x2, y2), confidence=confidence))
        return found


def load_fire_detector() -> FireSmokeDetector | None:
    """Load once at start-up; None if disabled, the weights are missing, or they are unusable
    (every other feature keeps working without it)."""
    if not settings.fire.enabled:
        logger.info("Fire and smoke detection disabled in settings")
        return None
    try:
        return FireSmokeDetector(settings.fire)
    except FileNotFoundError as exc:
        logger.warning("Fire and smoke detection is OFF: %s (see README, 'Fire and smoke detection')", exc)
    except Exception:
        logger.exception("Failed to load the fire/smoke model; fire and smoke detection disabled for all cameras")
    return None
