import logging
from datetime import datetime, timezone

import cv2
from sqlalchemy import select

from app.db.models import Event
from app.db.session import SessionLocal
from app.services.recording.paths import resolve_recording_path

logger = logging.getLogger(__name__)


def _is_playable(path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    cap = cv2.VideoCapture(str(path))
    try:
        return cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0
    finally:
        cap.release()


def recover_stale_events() -> None:
    """Events still marked "recording" at startup belong to a previous run
    that was killed (crash, kill -9, power loss) before it could finalize
    them. Close them out so they don't show as recording forever: playable
    files become "interrupted", unreadable ones "failed"."""
    with SessionLocal() as session:
        stale = session.scalars(select(Event).where(Event.status == "recording")).all()
        for event in stale:
            ok = bool(event.recording_path) and _is_playable(resolve_recording_path(event.recording_path))
            event.status = "interrupted" if ok else "failed"
            event.ended_at = event.ended_at or datetime.now(timezone.utc)
        if stale:
            session.commit()
            logger.warning("Recovered %d event(s) left in 'recording' state by a previous run", len(stale))
