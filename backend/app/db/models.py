from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Camera(Base):
    """A configured camera source. Live status (online/offline, people in
    frame) is runtime state owned by CameraManager, not stored here.

    `Event.camera_id` deliberately has no foreign key to this table, so
    deleting a camera keeps its event/recording history.
    """

    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    # "webcam" | "rtsp" | "http" | "file"
    type: Mapped[str] = mapped_column(String)
    # webcam: device index ("0"); rtsp/http: URL; file: name inside video_sources_dir
    source: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


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


class Person(Base):
    """A registered (known) person."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FaceSample(Base):
    """One enrolled face photo of a person.

    Only the 128-number face embedding and a small cropped thumbnail are
    kept — the uploaded photo itself is discarded. The embedding is what
    recognition compares against; it cannot be turned back into a photo.
    """

    __tablename__ = "face_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    embedding: Mapped[bytes] = mapped_column(LargeBinary)  # 128 x float32, L2-normalized
    image_path: Mapped[str] = mapped_column(String)  # thumbnail, relative to storage_dir
    detection_score: Mapped[float] = mapped_column(Float)
    face_px: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class FaceObservation(Base):
    """A face seen by a camera and what the system decided about it.

    Debounced like PersonDetection (not one row per frame). `label` is one of
    "known", "unknown", "uncertain" (= not confidently recognized).
    """

    __tablename__ = "face_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True, index=True)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String, index=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    detection_score: Mapped[float] = mapped_column(Float)
    snapshot_path: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class Alert(Base):
    """A persistent alert.

    Lifecycle: created unread and open -> marked read (`acknowledged_at`) ->
    resolved (`resolved_at`; by a person, or automatically by the system, e.g.
    a camera that came back online). `dedupe_key` stops the same ongoing
    condition (like "camera X offline") from creating a new alert every time.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # unknown_person | restricted_area | suspicious_activity | camera_offline
    type: Mapped[str] = mapped_column(String, index=True)
    # low | medium | high | critical
    severity: Mapped[str] = mapped_column(String, index=True)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(String)
    snapshot_path: Mapped[str | None] = mapped_column(String, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: zone name, dwell time, ...
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # "read"
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)  # username, or "system"


class Zone(Base):
    """A restricted area drawn on a camera's image.

    `points` is a JSON list of [x, y] pairs normalized to 0..1 (so it keeps
    working if the camera's resolution changes). A zone with a schedule is
    only enforced between `schedule_start` and `schedule_end` (local HH:MM,
    may cross midnight); without one it is enforced all the time.
    """

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    points: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    schedule_start: Mapped[str | None] = mapped_column(String, nullable=True)
    schedule_end: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, default="high")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)  # stored lowercase
    password_hash: Mapped[str] = mapped_column(String)  # scrypt, salted; never the password
    role: Mapped[str] = mapped_column(String, default="viewer")  # admin | viewer
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class UserSession(Base):
    """A login session. Only a keyed hash of the token is stored, so a leaked
    database can't be used to hijack sessions."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
