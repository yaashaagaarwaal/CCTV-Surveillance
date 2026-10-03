import logging
import sqlite3

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.api.events import iso_utc
from app.core.config import settings
from app.db.models import FaceObservation, FaceSample, Person
from app.db.session import SessionLocal
from app.security.deps import current_user, require_admin
from app.services.camera.manager import camera_manager
from app.services.faces.runtime import get_face_service
from app.services.faces.service import EnrollError, FaceService
from app.services.faces.storage import new_face_sample_path, resolve, write_private_jpeg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/people", tags=["people"], dependencies=[Depends(current_user)])


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class FromCamera(BaseModel):
    camera_id: str


def _require_service() -> FaceService:
    service = get_face_service()
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Face recognition is not available (disabled, or its models could not be loaded — see the backend log)",
        )
    return service


def _name_taken(session, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(func.count()).select_from(Person).where(func.lower(Person.name) == name.lower())
    if exclude_id:
        stmt = stmt.where(Person.id != exclude_id)
    return bool(session.scalar(stmt))


def _get_person_or_404(session, person_id: int) -> Person:
    person = session.get(Person, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail=f"Person {person_id} not found")
    return person


def _serialize(session, person: Person) -> dict:
    samples = session.scalars(select(FaceSample).where(FaceSample.person_id == person.id).order_by(FaceSample.id)).all()
    last_seen = session.scalar(
        select(func.max(FaceObservation.timestamp)).where(
            FaceObservation.person_id == person.id, FaceObservation.label == "known"
        )
    )
    return {
        "id": person.id,
        "name": person.name,
        "created_at": iso_utc(person.created_at),
        "last_seen": iso_utc(last_seen),
        "samples": [
            {"id": s.id, "quality": round(s.detection_score, 2), "face_px": s.face_px, "created_at": iso_utc(s.created_at)}
            for s in samples
        ],
    }


@router.get("/status")
def recognition_status():
    """Whether recognition is running, and the thresholds it is using."""
    service = get_face_service()
    cfg = settings.face
    return {
        "available": service is not None,
        "enabled": cfg.enabled,
        "people_count": service.people_count if service else 0,
        "sample_count": service.sample_count if service else 0,
        "known_threshold": cfg.known_threshold,
        "unknown_threshold": cfg.unknown_threshold,
        "min_face_px": cfg.min_face_px,
        "unknown_confirmations": cfg.unknown_confirmations,
        "alert_cooldown_seconds": cfg.alert_cooldown_seconds,
    }


@router.get("")
def list_people():
    with SessionLocal() as session:
        people = session.scalars(select(Person).order_by(func.lower(Person.name))).all()
        return [_serialize(session, p) for p in people]


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
def create_person(body: PersonCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name is required")
    with SessionLocal() as session:
        if _name_taken(session, name):
            raise HTTPException(status_code=409, detail=f"'{name}' is already registered")
        person = Person(name=name)
        session.add(person)
        session.commit()
        return _serialize(session, person)


@router.get("/{person_id}")
def get_person(person_id: int):
    with SessionLocal() as session:
        return _serialize(session, _get_person_or_404(session, person_id))


@router.patch("/{person_id}", dependencies=[Depends(require_admin)])
def rename_person(person_id: int, body: PersonCreate):
    name = body.name.strip()
    with SessionLocal() as session:
        person = _get_person_or_404(session, person_id)
        if _name_taken(session, name, exclude_id=person_id):
            raise HTTPException(status_code=409, detail=f"'{name}' is already registered")
        person.name = name
        session.commit()
        result = _serialize(session, person)
    service = get_face_service()
    if service:
        service.reload_gallery()  # names are cached with the embeddings
    return result


@router.delete("/{person_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_person(person_id: int):
    """Delete a person and all of their face data (embeddings + thumbnails).
    Past observations are kept but no longer linked to anyone."""
    with SessionLocal() as session:
        _get_person_or_404(session, person_id)
        samples = session.scalars(select(FaceSample).where(FaceSample.person_id == person_id)).all()
        for sample in samples:
            resolve(sample.image_path).unlink(missing_ok=True)
        session.execute(delete(FaceSample).where(FaceSample.person_id == person_id))
        session.execute(update(FaceObservation).where(FaceObservation.person_id == person_id).values(person_id=None))
        session.delete(session.get(Person, person_id))
        session.commit()
    service = get_face_service()
    if service:
        service.reload_gallery()
    return Response(status_code=204)


def _enroll_image(service: FaceService, session, person_id: int, image: np.ndarray) -> dict:
    result = service.enroll(image)  # raises EnrollError with a user-facing reason
    path = new_face_sample_path(person_id)
    write_private_jpeg(resolve(str(path)), result.thumbnail)
    sample = FaceSample(
        person_id=person_id,
        embedding=result.embedding.astype(np.float32).tobytes(),
        image_path=str(path),
        detection_score=result.score,
        face_px=result.face_px,
    )
    session.add(sample)
    session.commit()
    return {"sample_id": sample.id}


def _process_uploads(service: FaceService, person_id: int, uploads: list[tuple[str | None, bytes]]) -> dict:
    cfg = settings.face
    results = []
    for filename, data in uploads:
        entry = {"filename": filename, "ok": False, "error": None}
        try:
            if len(data) > cfg.enroll_max_image_bytes:
                raise EnrollError(f"Photo is larger than {cfg.enroll_max_image_bytes // (1024 * 1024)} MB")
            image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise EnrollError("Not a readable image (use JPEG or PNG)")
            with SessionLocal() as session:
                entry.update(_enroll_image(service, session, person_id, image), ok=True)
        except EnrollError as exc:
            entry["error"] = str(exc)
        except (cv2.error, OSError, SQLAlchemyError, sqlite3.Error):
            logger.exception("Registering photo %s failed", filename)
            entry["error"] = "Could not process this photo"
        results.append(entry)

    service.reload_gallery()
    with SessionLocal() as session:
        return {"results": results, "person": _serialize(session, session.get(Person, person_id))}


@router.post("/{person_id}/faces", dependencies=[Depends(require_admin)])
async def add_face_photos(person_id: int, files: list[UploadFile] = File(...)):
    """Register one or more photos. Each photo is checked on its own; the
    response says which were accepted and why any were rejected. The photos
    themselves are not kept — only the face embedding and a small thumbnail."""
    service = _require_service()
    cfg = settings.face
    if len(files) > cfg.enroll_max_images_per_request:
        raise HTTPException(status_code=422, detail=f"At most {cfg.enroll_max_images_per_request} photos at a time")
    with SessionLocal() as session:
        _get_person_or_404(session, person_id)

    # Read uploads here (async), then do the CPU-heavy work off the event loop
    # so live streams aren't stalled while photos are processed.
    uploads = [(f.filename, await f.read(cfg.enroll_max_image_bytes + 1)) for f in files]
    return await run_in_threadpool(_process_uploads, service, person_id, uploads)


@router.post("/{person_id}/faces/from-camera", dependencies=[Depends(require_admin)])
def add_face_from_camera(person_id: int, body: FromCamera):
    """Register a face from a camera's current frame (the person looks at the camera)."""
    service = _require_service()
    with SessionLocal() as session:
        _get_person_or_404(session, person_id)

    worker = camera_manager.get(body.camera_id)
    frame = worker.get_latest_frame() if worker else None
    if frame is None:
        raise HTTPException(status_code=409, detail="That camera is not online right now")

    with SessionLocal() as session:
        try:
            _enroll_image(service, session, person_id, frame)
        except EnrollError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        service.reload_gallery()
        return _serialize(session, session.get(Person, person_id))


@router.get("/{person_id}/faces/{sample_id}/image")
def face_sample_image(person_id: int, sample_id: int):
    with SessionLocal() as session:
        sample = session.get(FaceSample, sample_id)
        if sample is None or sample.person_id != person_id:
            raise HTTPException(status_code=404, detail="Face sample not found")
        path = resolve(sample.image_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Face image file is missing")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{person_id}/faces/{sample_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_face_sample(person_id: int, sample_id: int):
    with SessionLocal() as session:
        sample = session.get(FaceSample, sample_id)
        if sample is None or sample.person_id != person_id:
            raise HTTPException(status_code=404, detail="Face sample not found")
        resolve(sample.image_path).unlink(missing_ok=True)
        session.delete(sample)
        session.commit()
    service = get_face_service()
    if service:
        service.reload_gallery()
    return Response(status_code=204)
