from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    """One motion-triggered recording.

    `event_type` starts as "motion" and is upgraded to "person" the moment
    YOLO confirms a person appeared during the recording (see
    MotionEventPipeline). `recording_path` is stored relative to
    `settings.storage_dir` (never an absolute path) so the database stays
    portable across machines.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String, default="motion")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    recording_path: Mapped[str | None] = mapped_column(String, nullable=True)
    # "recording" -> "completed" | "failed" | "interrupted" (app shut down mid-clip)
    status: Mapped[str] = mapped_column(String, default="recording")
    # Highest YOLO confidence seen for a person during this event, if any.
    max_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class PersonDetection(Base):
    """One person appearing in frame.

    Debounced, not per-frame: a new row is only written when a person is
    first noticed after the frame had nobody in it (see
    MotionEventPipeline._run_person_detection), so a person standing in
    frame for 20 seconds produces one row, not dozens.
    """

    __tablename__ = "person_detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True, index=True)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    bbox_x1: Mapped[int] = mapped_column(Integer)
    bbox_y1: Mapped[int] = mapped_column(Integer)
    bbox_x2: Mapped[int] = mapped_column(Integer)
    bbox_y2: Mapped[int] = mapped_column(Integer)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
