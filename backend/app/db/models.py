from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(Base):
    """One motion-triggered recording.

    `recording_path` is stored relative to `settings.storage_dir` (never an
    absolute path) so the database stays portable across machines.
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
