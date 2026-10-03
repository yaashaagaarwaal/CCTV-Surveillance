import logging
import time
from datetime import datetime, timezone

import cv2
import numpy as np

from app.core.config import FaceConfig, settings
from app.db.models import Event, FaceObservation
from app.db.session import SessionLocal
from app.services.alerts import raise_alert
from app.services.faces.service import LABEL_KNOWN, LABEL_UNCERTAIN, LABEL_UNKNOWN, FaceResult
from app.services.faces.storage import new_snapshot_path, resolve, write_private_jpeg
from app.services.recording.event_types import upgrade_event_type

logger = logging.getLogger(__name__)

LABEL_COLORS = {  # BGR
    LABEL_KNOWN: (0, 200, 0),
    LABEL_UNKNOWN: (0, 0, 230),
    LABEL_UNCERTAIN: (0, 165, 255),
}


def draw_faces(frame: np.ndarray, faces: list[FaceResult]) -> None:
    """Draw face boxes with a label: green=known, red=unknown, orange=not sure."""
    for face in faces:
        x, y, w, h = face.bbox
        color = LABEL_COLORS[face.label]
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        if face.label == LABEL_KNOWN:
            text = f"{face.name} {face.similarity:.2f}"
        elif face.label == LABEL_UNKNOWN:
            text = "UNKNOWN"
        else:
            text = "NOT SURE"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        top = min(y + h + th + 8, frame.shape[0] - 2)
        cv2.rectangle(frame, (x, top - th - 6), (x + tw + 6, top + 2), color, -1)
        cv2.putText(frame, text, (x + 3, top - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)


class FaceEventTracker:
    """Turns raw per-cycle recognition results into events and alerts.

    One per camera, living inside MotionEventPipeline. Recognition results
    are noisy, so nothing is decided from a single frame:
      * known / not-sure faces are logged at most once per interval,
      * an UNKNOWN person needs `unknown_confirmations` separate recognition
        cycles inside one recording before an unknown-person event, snapshot
        and alert are created,
      * alerts are rate-limited per camera (`alert_cooldown_seconds`).
    """

    def __init__(self, camera_id: str, config: FaceConfig):
        self.camera_id = camera_id
        self.config = config
        self._last_logged: dict[str, float] = {}
        self._unknown_cycles = 0
        self._unknown_confirmed = False
        self._last_alert_at: float | None = None  # survives across recordings

    def reset_event(self) -> None:
        self._last_logged.clear()
        self._unknown_cycles = 0
        self._unknown_confirmed = False

    def handle(
        self, faces: list[FaceResult], frame: np.ndarray, event_id: int | None, people_registered: int, night: bool = False
    ) -> None:
        now = time.monotonic()
        unknown_faces = []

        for face in faces:
            if face.label == LABEL_KNOWN:
                self._log_observation(f"known:{face.person_id}", face, event_id, now)
            elif face.label == LABEL_UNCERTAIN:
                self._log_observation("uncertain", face, event_id, now)
            elif people_registered > 0:
                # With nobody registered there is nothing to be "unknown"
                # relative to, so no unknown events/alerts are created.
                unknown_faces.append(face)

        if unknown_faces and not self._unknown_confirmed:
            self._unknown_cycles += 1
            needed = max(self.config.unknown_confirmations, settings.night.unknown_confirmations) if night else self.config.unknown_confirmations
            if self._unknown_cycles >= needed:
                self._confirm_unknown(unknown_faces, frame, event_id, now)

    def _log_observation(self, key: str, face: FaceResult, event_id: int | None, now: float) -> None:
        last = self._last_logged.get(key)
        if last is not None and now - last < self.config.observation_interval_seconds:
            return
        self._last_logged[key] = now
        with SessionLocal() as session:
            session.add(
                FaceObservation(
                    event_id=event_id,
                    camera_id=self.camera_id,
                    person_id=face.person_id,
                    label=face.label,
                    similarity=face.similarity,
                    detection_score=face.score,
                    timestamp=datetime.now(timezone.utc),
                )
            )
            session.commit()
        logger.info(
            "Camera %s: face %s%s", self.camera_id, face.label, f" ({face.name}, {face.similarity:.2f})" if face.name else ""
        )

    def _confirm_unknown(self, unknown_faces: list[FaceResult], frame: np.ndarray, event_id: int | None, now: float) -> None:
        self._unknown_confirmed = True
        best = max(unknown_faces, key=lambda f: f.score)
        when = datetime.now(timezone.utc)

        snapshot_rel = None
        try:
            annotated = frame.copy()
            draw_faces(annotated, unknown_faces)
            path = new_snapshot_path(self.camera_id, when)
            write_private_jpeg(resolve(str(path)), annotated)
            snapshot_rel = str(path)
        except Exception:
            logger.exception("Camera %s: could not save unknown-person snapshot", self.camera_id)

        with SessionLocal() as session:
            session.add(
                FaceObservation(
                    event_id=event_id,
                    camera_id=self.camera_id,
                    label=LABEL_UNKNOWN,
                    similarity=best.similarity,
                    detection_score=best.score,
                    snapshot_path=snapshot_rel,
                    timestamp=when,
                )
            )
            if event_id is not None:
                event = session.get(Event, event_id)
                if event is not None:
                    upgrade_event_type(event, "unknown_person")
            session.commit()

        cooldown = self.config.alert_cooldown_seconds
        if self._last_alert_at is not None and now - self._last_alert_at < cooldown:
            logger.info("Camera %s: unknown person recorded; alert suppressed (cooldown)", self.camera_id)
            return
        self._last_alert_at = now
        raise_alert(
            alert_type="unknown_person",
            severity="high",
            camera_id=self.camera_id,
            message="Unknown person detected",
            event_id=event_id,
            snapshot_path=snapshot_rel,
        )
