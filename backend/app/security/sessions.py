import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import delete, select

from app.core.config import BASE_DIR, settings
from app.db.models import User, UserSession
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)
SECRET_FILE = BASE_DIR / "data" / ".secret_key"


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def utcnow() -> datetime:
    """Naive UTC, the form SQLite gives datetimes back in."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@lru_cache(maxsize=1)
def _secret() -> bytes:
    """Key used to hash session tokens: SECRET_KEY from the environment, or
    one generated once and kept in data/.secret_key (owner-only)."""
    if settings.secret_key:
        if len(settings.secret_key) < 16:
            raise RuntimeError("SECRET_KEY must be at least 16 characters")
        return settings.secret_key.encode()
    if not SECRET_FILE.is_file():
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(48))
        logger.info("Generated a session secret key at %s", SECRET_FILE)
    return SECRET_FILE.read_text().strip().encode()


def hash_token(token: str) -> str:
    return hmac.new(_secret(), token.encode(), hashlib.sha256).hexdigest()


def create_session(user_id: int, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)  # 256 bits; only its keyed hash is stored
    now = utcnow()
    with SessionLocal() as db:
        db.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user_id,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(hours=settings.security.session_hours),
                ip=ip,
                user_agent=(user_agent or "")[:200] or None,
            )
        )
        db.commit()
    return token


def lookup_session(token: str | None) -> AuthUser | None:
    """The user a session token belongs to, or None. Enforces idle expiry,
    absolute lifetime and disabled accounts, and slides the idle window."""
    if not token:
        return None
    now = utcnow()
    with SessionLocal() as db:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
        if session is None:
            return None
        absolute_end = session.created_at + timedelta(days=settings.security.session_max_days)
        if session.expires_at <= now or absolute_end <= now:
            db.delete(session)
            db.commit()
            return None
        user = db.get(User, session.user_id)
        if user is None or user.disabled:
            return None
        if (now - session.last_seen_at).total_seconds() > 60:  # avoid a write on every request
            session.last_seen_at = now
            session.expires_at = min(now + timedelta(hours=settings.security.session_hours), absolute_end)
            db.commit()
        return AuthUser(user.id, user.username, user.role)


def revoke_token(token: str | None) -> None:
    if token:
        with SessionLocal() as db:
            db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
            db.commit()


def revoke_user_sessions(user_id: int, except_token: str | None = None) -> None:
    keep = hash_token(except_token) if except_token else None
    with SessionLocal() as db:
        stmt = delete(UserSession).where(UserSession.user_id == user_id)
        if keep:
            stmt = stmt.where(UserSession.token_hash != keep)
        db.execute(stmt)
        db.commit()


def purge_expired_sessions() -> None:
    with SessionLocal() as db:
        db.execute(delete(UserSession).where(UserSession.expires_at <= utcnow()))
        db.commit()
