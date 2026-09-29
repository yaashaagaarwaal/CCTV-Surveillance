import logging
import time
from datetime import datetime, timezone

import numpy as np

from app.core.config import settings
from app.db.models import Event
from app.db.session import SessionLocal
from app.services.motion.detector import MotionDetector
from app.services.recording.paths import build_recording_path, resolve_recording_path
from app.services.recording.writer import RecordingWriter

logger = logging.getLogger(__name__)


class MotionEventPipeline:
    """Per-camera: feed it frames, it detects motion and manages recordings.

    Runs entirely inside the camera's own capture thread (see
    CameraWorker._run) — there is no separate recording thread. That thread
    is already a background thread relative to FastAPI's event loop/HTTP
    handling, so the live stream (served from a lock-protected "latest
    frame" the capture thread updates independently) is never blocked by
    motion detection or video encoding here; at most, heavy encoding adds a
    little latency to this camera's own capture loop, never to the HTTP
    server or other cameras.
    """

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        cfg = settings.motion
        self._detector = MotionDetector(
            sensitivity=cfg.sensitivity,
            min_area=cfg.min_area,
            warmup_frames=cfg.warmup_frames,
        )
        self._writer: RecordingWriter | None = None
        self._event_id: int | None = None
        self._recording_started_at: float = 0.0
        self._last_motion_at: float = 0.0
        self._last_event_ended_at: float | None = None

    def process(self, frame: np.ndarray) -> None:
        motion = self._detector.process(frame)
        now = time.monotonic()

        if self._writer is not None:
            self._writer.write(frame)
            if motion:
                self._last_motion_at = now

            recording_age = now - self._recording_started_at
            idle_time = now - self._last_motion_at
            cfg = settings.motion
            if idle_time >= cfg.post_motion_seconds or recording_age >= cfg.max_recording_seconds:
                self._finalize(status="completed")
            return

        if not motion:
            return

        if self._last_event_ended_at is not None:
            if now - self._last_event_ended_at < settings.motion.cooldown_seconds:
                return  # still cooling down since the last event ended

        self._start(frame)

    def _start(self, frame: np.ndarray) -> None:
        started_at = datetime.now(timezone.utc)
        relative_path = build_recording_path(self.camera_id, started_at)
        absolute_path = resolve_recording_path(str(relative_path))

        height, width = frame.shape[:2]
        self._writer = RecordingWriter(absolute_path, fps=settings.capture_fps, frame_size=(width, height))

        with SessionLocal() as session:
            event = Event(
                camera_id=self.camera_id,
                event_type="motion",
                timestamp=started_at,
                recording_path=str(relative_path),
                status="recording",
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            self._event_id = event.id

        now = time.monotonic()
        self._recording_started_at = now
        self._last_motion_at = now
        logger.info("Camera %s: motion detected, recording event %s", self.camera_id, self._event_id)

    def _finalize(self, status: str) -> None:
        if self._writer is None:
            return

        recorded_path = self._writer.path
        self._writer.close()
        self._writer = None

        file_ok = recorded_path.is_file() and recorded_path.stat().st_size > 0
        final_status = status if file_ok else "failed"

        if self._event_id is not None:
            with SessionLocal() as session:
                event = session.get(Event, self._event_id)
                if event is not None:
                    event.ended_at = datetime.now(timezone.utc)
                    event.status = final_status
                    session.commit()
            logger.info("Camera %s: event %s finalized as %s", self.camera_id, self._event_id, final_status)

        self._event_id = None
        self._last_event_ended_at = time.monotonic()

    def close(self) -> None:
        """Called when the camera worker stops (app shutdown or camera loss)."""
        if self._writer is not None:
            self._finalize(status="interrupted")
