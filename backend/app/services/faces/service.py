import logging
import shutil
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from sqlalchemy import select

from app.core.config import FaceConfig
from app.db.models import FaceSample, Person
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

DETECT_MAX_WIDTH = 640  # faces are found on a downscaled copy; embeddings use the full-resolution frame
THUMBNAIL_SIZE = 200
LABEL_KNOWN, LABEL_UNKNOWN, LABEL_UNCERTAIN = "known", "unknown", "uncertain"


class EnrollError(ValueError):
    """A photo can't be used for registration (message is shown to the user)."""


@dataclass
class FaceBox:
    x: int
    y: int
    w: int
    h: int
    score: float
    row: np.ndarray  # YuNet row in full-frame pixels (box + 5 landmarks + score)

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.w / 2, self.y + self.h / 2

    @property
    def yaw_ratio(self) -> float:
        """~0 when facing the camera, grows as the head turns sideways."""
        right_eye, left_eye, nose = self.row[4:6], self.row[6:8], self.row[8:10]
        eye_distance = float(np.linalg.norm(right_eye - left_eye))
        if eye_distance < 1:
            return 1.0
        return abs(float(nose[0] - (right_eye[0] + left_eye[0]) / 2)) / eye_distance


@dataclass
class FaceResult:
    bbox: tuple[int, int, int, int]  # x, y, w, h
    score: float
    label: str  # known | unknown | uncertain
    person_id: int | None = None
    name: str | None = None
    similarity: float | None = None  # best cosine similarity to anyone registered
    reason: str | None = None  # why it is "uncertain"


@dataclass
class EnrollResult:
    embedding: np.ndarray
    thumbnail: np.ndarray
    score: float
    face_px: int


class Gallery:
    """All enrolled embeddings in one matrix, so matching a face is a single
    matrix product. Replaced wholesale on change, never edited in place."""

    def __init__(self, person_ids: list[int], names: list[str], embeddings: list[np.ndarray]):
        self.person_ids = person_ids
        self.names = names
        self.matrix = np.vstack(embeddings).astype(np.float32) if embeddings else np.zeros((0, 128), np.float32)
        self.people_count = len(set(person_ids))

    def best_match(self, embedding: np.ndarray) -> tuple[int, str, float] | None:
        if len(self.person_ids) == 0:
            return None
        sims = self.matrix @ embedding
        i = int(np.argmax(sims))
        return self.person_ids[i], self.names[i], float(sims[i])


def ensure_model(path: Path, url: str, min_bytes: int) -> None:
    """Download a model file on first use (verified by size, written atomically)."""
    if path.is_file() and path.stat().st_size >= min_bytes:
        return
    logger.info("Downloading %s ...", path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, open(partial, "wb") as out:
        shutil.copyfileobj(response, out)
    if partial.stat().st_size < min_bytes:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded {path.name} looks incomplete")
    partial.replace(path)


def _normalize(vector: np.ndarray) -> np.ndarray:
    vector = vector.flatten().astype(np.float32)
    return vector / (np.linalg.norm(vector) or 1.0)


class FaceService:
    """Face detection + recognition, shared by every camera and the API.

    Pipeline per face: YuNet detects it (and 5 landmarks) -> SFace aligns the
    face with those landmarks and turns it into a 128-number embedding ->
    cosine similarity against every enrolled embedding -> thresholds decide
    known / unknown / not confidently recognized.

    OpenCV's DNN modules aren't guaranteed thread-safe, so all model calls
    are serialized with one lock (recognition only runs on a few frames per
    second, so contention is negligible).
    """

    def __init__(self, config: FaceConfig):
        self.config = config
        ensure_model(config.detector_model_path, config.detector_model_url, 100_000)
        ensure_model(config.recognizer_model_path, config.recognizer_model_url, 30_000_000)
        self._detector = cv2.FaceDetectorYN.create(
            str(config.detector_model_path), "", (320, 320), config.min_detection_score, 0.3, 500
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(config.recognizer_model_path), "")
        self._lock = threading.Lock()
        self._gallery = Gallery([], [], [])
        self.reload_gallery()
        self._detect(np.zeros((240, 320, 3), np.uint8))  # warm up
        logger.info("Face recognition ready (%d registered people)", self._gallery.people_count)

    # ---- gallery ---------------------------------------------------------

    def reload_gallery(self) -> None:
        """Re-read all enrolled faces from the database (call after any change)."""
        with SessionLocal() as session:
            rows = session.execute(
                select(FaceSample.person_id, Person.name, FaceSample.embedding).join(Person, Person.id == FaceSample.person_id)
            ).all()
        self._gallery = Gallery(
            [r[0] for r in rows], [r[1] for r in rows], [np.frombuffer(r[2], dtype=np.float32) for r in rows]
        )

    @property
    def people_count(self) -> int:
        return self._gallery.people_count

    @property
    def sample_count(self) -> int:
        return len(self._gallery.person_ids)

    # ---- model calls (callers hold self._lock, except __init__ warm-up) ----

    def _detect(self, frame: np.ndarray) -> list[FaceBox]:
        height, width = frame.shape[:2]
        scale = min(1.0, DETECT_MAX_WIDTH / width)
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1.0 else frame
        self._detector.setInputSize((small.shape[1], small.shape[0]))
        _, rows = self._detector.detect(small)
        if rows is None:
            return []
        boxes = []
        for row in rows:
            full = row.copy()
            full[:14] = full[:14] / scale
            x, y, w, h = (int(round(v)) for v in full[:4])
            boxes.append(FaceBox(max(x, 0), max(y, 0), w, h, float(full[14]), full))
        return boxes

    def _embed(self, frame: np.ndarray, box: FaceBox) -> np.ndarray:
        aligned = self._recognizer.alignCrop(frame, box.row)
        return _normalize(self._recognizer.feature(aligned))

    # ---- live recognition --------------------------------------------------

    def analyze(
        self,
        frame: np.ndarray,
        regions: list[tuple[int, int, int, int]] | None = None,
        brightness_frame: np.ndarray | None = None,
    ) -> list[FaceResult]:
        """Find and classify every face in `frame`.

        `regions` (x1, y1, x2, y2) restricts this to faces whose center lies
        inside one of them — in the pipeline, the people YOLO just found.

        `brightness_frame` is the un-enhanced frame: how dark a face really is
        must be judged on what the camera captured, not on a brightened copy.
        """
        results = []
        gallery = self._gallery
        gray = cv2.cvtColor(brightness_frame if brightness_frame is not None else frame, cv2.COLOR_BGR2GRAY)
        with self._lock:
            for box in self._detect(frame):
                if regions is not None:
                    cx, cy = box.center
                    if not any(x1 <= cx <= x2 and y1 <= cy <= y2 for x1, y1, x2, y2 in regions):
                        continue
                face_gray = gray[box.y : box.y + box.h, box.x : box.x + box.w]
                brightness = float(face_gray.mean()) if face_gray.size else 0.0
                results.append(self._classify(box, self._embed(frame, box), gallery, brightness))
        return results

    def _classify(self, box: FaceBox, embedding: np.ndarray, gallery: Gallery, brightness: float = 255.0) -> FaceResult:
        cfg = self.config
        match = gallery.best_match(embedding)
        similarity = match[2] if match else None
        base = dict(bbox=(box.x, box.y, box.w, box.h), score=box.score, similarity=similarity)

        if match and similarity >= cfg.known_threshold:
            return FaceResult(label=LABEL_KNOWN, person_id=match[0], name=match[1], **base)

        # Not a confident match. Only call it "unknown" when the face is good
        # enough that a poor score really means "someone else".
        if brightness < cfg.min_face_brightness:
            return FaceResult(label=LABEL_UNCERTAIN, reason="too dark to judge", **base)
        if min(box.w, box.h) < cfg.min_face_px:
            return FaceResult(label=LABEL_UNCERTAIN, reason="face too small", **base)
        if box.yaw_ratio > cfg.max_yaw_ratio:
            return FaceResult(label=LABEL_UNCERTAIN, reason="face turned away", **base)
        if match is None or similarity < cfg.unknown_threshold:
            return FaceResult(label=LABEL_UNKNOWN, **base)
        return FaceResult(label=LABEL_UNCERTAIN, reason="similarity between thresholds", **base)

    # ---- registration ------------------------------------------------------

    def enroll(self, image: np.ndarray) -> EnrollResult:
        """Validate a registration photo and extract its embedding + thumbnail."""
        cfg = self.config
        with self._lock:
            boxes = sorted(self._detect(image), key=lambda b: b.w * b.h, reverse=True)
            if not boxes:
                raise EnrollError("No face found in this photo")
            main = boxes[0]
            if len(boxes) > 1 and boxes[1].w * boxes[1].h > 0.4 * main.w * main.h:
                raise EnrollError("More than one face in this photo — use a photo of just this person")
            if min(main.w, main.h) < cfg.enroll_min_face_px:
                raise EnrollError(f"Face is too small ({min(main.w, main.h)}px, need {cfg.enroll_min_face_px}px) — use a closer photo")
            if main.score < cfg.enroll_min_detection_score:
                raise EnrollError(f"Face is not clear enough (detector confidence {main.score:.2f}, need {cfg.enroll_min_detection_score:.2f}) — use a sharper, well-lit photo")
            if main.yaw_ratio > cfg.enroll_max_yaw_ratio:
                raise EnrollError("Face is turned too far sideways — use a more frontal photo")
            embedding = self._embed(image, main)
        return EnrollResult(embedding, self._thumbnail(image, main), main.score, min(main.w, main.h))

    @staticmethod
    def _thumbnail(image: np.ndarray, box: FaceBox) -> np.ndarray:
        cx, cy = box.center
        half = int(max(box.w, box.h) * 0.7)
        x1, y1 = max(int(cx) - half, 0), max(int(cy) - half, 0)
        crop = image[y1 : int(cy) + half, x1 : int(cx) + half]
        return cv2.resize(crop, (THUMBNAIL_SIZE, THUMBNAIL_SIZE), interpolation=cv2.INTER_AREA)


def load_face_service(config: FaceConfig) -> FaceService | None:
    """Create the shared service; None if disabled or it can't start (e.g.
    models can't be downloaded offline). The CCTV pipeline works without it."""
    if not config.enabled:
        logger.info("Face recognition disabled in settings")
        return None
    try:
        return FaceService(config)
    except Exception:
        logger.exception("Face recognition could not start; continuing without it")
        return None
