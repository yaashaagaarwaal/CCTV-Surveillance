import logging
from datetime import datetime, timezone

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select

from app.db.models import Event, FaceObservation, Person, PersonDetection
from app.db.session import SessionLocal
from app.security.deps import current_user, require_admin
from app.services.recording.paths import resolve_recording_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"], dependencies=[Depends(current_user)])

# A recording can only be played once it has been finalized and closed.
PLAYABLE_STATUSES = ("completed", "interrupted")
THUMBNAIL_WIDTH = 480


def iso_utc(value: datetime | None) -> str | None:
    """SQLite hands back naive datetimes that are really UTC. Without an
    explicit 'Z' the browser would parse them as local time and show every
    timestamp shifted by the user's UTC offset."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _faces_summary(session, event_ids: list[int]) -> dict[int, dict]:
    """Who was recognized in each event: known names plus unknown/not-sure counts."""
    summary = {i: {"people": [], "unknown_faces": 0, "uncertain_faces": 0} for i in event_ids}
    if not event_ids:
        return summary
    rows = session.execute(
        select(FaceObservation.event_id, FaceObservation.label, Person.name)
        .join(Person, Person.id == FaceObservation.person_id, isouter=True)
        .where(FaceObservation.event_id.in_(event_ids))
    ).all()
    for event_id, label, name in rows:
        entry = summary[event_id]
        if label == "known":
            name = name or "Deleted person"  # their registration was removed later
            if name not in entry["people"]:
                entry["people"].append(name)
        elif label == "unknown":
            entry["unknown_faces"] += 1
        elif label == "uncertain":
            entry["uncertain_faces"] += 1
    return summary


def _serialize(event: Event, faces: dict | None = None) -> dict:
    size_bytes = None
    if event.recording_path:
        path = resolve_recording_path(event.recording_path)
        if path.is_file():
            size_bytes = path.stat().st_size
    return {
        "id": event.id,
        "camera_id": event.camera_id,
        "event_type": event.event_type,
        "timestamp": iso_utc(event.timestamp),
        "ended_at": iso_utc(event.ended_at),
        "status": event.status,
        "has_recording": bool(event.recording_path),
        "playable": bool(event.recording_path) and event.status in PLAYABLE_STATUSES and size_bytes is not None,
        "size_bytes": size_bytes,
        "max_confidence": event.max_confidence,
        **(faces or {"people": [], "unknown_faces": 0, "uncertain_faces": 0}),
    }


def _get_event_or_404(session, event_id: int) -> Event:
    event = session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return event


@router.get("")
def list_events(
    camera_id: str | None = None,
    event_type: str | None = None,
    status: str | None = None,
    recordings_only: bool = False,
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Newest first. `recordings_only` = events whose clip can be played."""
    conditions = []
    if camera_id:
        conditions.append(Event.camera_id == camera_id)
    if event_type:
        conditions.append(Event.event_type == event_type)
    if status:
        conditions.append(Event.status == status)
    if recordings_only:
        conditions += [Event.recording_path.is_not(None), Event.status.in_(PLAYABLE_STATUSES)]
    if since:
        conditions.append(Event.timestamp >= since.astimezone(timezone.utc).replace(tzinfo=None))

    with SessionLocal() as session:
        total = session.scalar(select(func.count()).select_from(Event).where(*conditions))
        events = session.scalars(
            select(Event).where(*conditions).order_by(Event.timestamp.desc(), Event.id.desc()).limit(limit).offset(offset)
        ).all()
        faces = _faces_summary(session, [e.id for e in events])
        return {"items": [_serialize(e, faces[e.id]) for e in events], "total": total or 0}


@router.get("/{event_id}")
def get_event(event_id: int):
    with SessionLocal() as session:
        event = _get_event_or_404(session, event_id)
        return _serialize(event, _faces_summary(session, [event_id])[event_id])


def _playable_path_or_404(event: Event):
    if not event.recording_path:
        raise HTTPException(status_code=404, detail="This event has no recording")
    if event.status not in PLAYABLE_STATUSES:
        raise HTTPException(status_code=404, detail=f"Recording is not available (status: {event.status})")
    path = resolve_recording_path(event.recording_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Recording file is missing or was deleted")
    return path


@router.get("/{event_id}/video")
def get_event_video(event_id: int):
    with SessionLocal() as session:
        event = _get_event_or_404(session, event_id)
    path = _playable_path_or_404(event)
    return FileResponse(path, media_type="video/mp4", filename=path.name, content_disposition_type="inline")


@router.get("/{event_id}/download")
def download_event_video(event_id: int):
    with SessionLocal() as session:
        event = _get_event_or_404(session, event_id)
    path = _playable_path_or_404(event)
    return FileResponse(path, media_type="video/mp4", filename=path.name, content_disposition_type="attachment")


def _make_thumbnail(video_path, thumb_path) -> bool:
    cap = cv2.VideoCapture(str(video_path))
    try:
        if not cap.isOpened():
            return False
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total > 1:
            cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
        ok, frame = cap.read()
        if not ok or frame is None:
            return False
        height, width = frame.shape[:2]
        if width > THUMBNAIL_WIDTH:
            frame = cv2.resize(frame, (THUMBNAIL_WIDTH, int(height * THUMBNAIL_WIDTH / width)))
        return bool(cv2.imwrite(str(thumb_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 80]))
    except cv2.error:
        logger.exception("Could not create thumbnail for %s", video_path)
        return False
    finally:
        cap.release()


@router.get("/{event_id}/thumbnail")
def get_event_thumbnail(event_id: int):
    """Middle frame of the clip, generated on first request and cached on
    disk next to the video."""
    with SessionLocal() as session:
        event = _get_event_or_404(session, event_id)
    video_path = _playable_path_or_404(event)
    thumb_path = video_path.with_suffix(".jpg")
    if not thumb_path.is_file() and not _make_thumbnail(video_path, thumb_path):
        raise HTTPException(status_code=404, detail="Thumbnail unavailable (recording may be corrupted)")
    return FileResponse(thumb_path, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@router.delete("/{event_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_event(event_id: int):
    """Delete an event together with its recording file and thumbnail."""
    with SessionLocal() as session:
        event = _get_event_or_404(session, event_id)
        if event.status == "recording":
            raise HTTPException(status_code=409, detail="This event is still recording")
        if event.recording_path:
            video_path = resolve_recording_path(event.recording_path)
            for path in (video_path, video_path.with_suffix(".jpg")):
                path.unlink(missing_ok=True)
        session.execute(delete(PersonDetection).where(PersonDetection.event_id == event_id))
        session.execute(delete(FaceObservation).where(FaceObservation.event_id == event_id))
        session.delete(event)
        session.commit()
    return Response(status_code=204)
