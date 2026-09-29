from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.db.models import Event
from app.db.session import SessionLocal
from app.services.recording.paths import resolve_recording_path

router = APIRouter(prefix="/events", tags=["events"])


def _serialize(event: Event) -> dict:
    return {
        "id": event.id,
        "camera_id": event.camera_id,
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat(),
        "ended_at": event.ended_at.isoformat() if event.ended_at else None,
        "status": event.status,
        "has_recording": bool(event.recording_path),
    }


def _get_event_or_404(session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return event


@router.get("")
def list_events(camera_id: str | None = None, limit: int = Query(50, ge=1, le=200)):
    with SessionLocal() as session:
        stmt = select(Event).order_by(Event.timestamp.desc()).limit(limit)
        if camera_id:
            stmt = stmt.where(Event.camera_id == camera_id)
        events = session.scalars(stmt).all()
        return [_serialize(e) for e in events]


@router.get("/{event_id}")
def get_event(event_id: int):
    with SessionLocal() as session:
        return _serialize(_get_event_or_404(session, event_id))


@router.get("/{event_id}/video")
def get_event_video(event_id: int):
    with SessionLocal() as session:
        event = _get_event_or_404(session, event_id)

    if not event.recording_path:
        raise HTTPException(status_code=404, detail="This event has no recording")

    full_path = resolve_recording_path(event.recording_path)
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Recording file is missing or was deleted")

    return FileResponse(
        full_path,
        media_type="video/mp4",
        filename=full_path.name,
        content_disposition_type="inline",
    )
