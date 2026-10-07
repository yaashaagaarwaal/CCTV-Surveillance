import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from starlette.concurrency import run_in_threadpool

from app.core.shutdown import shutdown_event
from app.db.models import Camera, CameraRules, Zone
from app.security.deps import current_user, require_admin
from app.security.sessions import AuthUser
from app.db.session import SessionLocal
from app.services.camera.factory import CameraSpec, SourceError, build_camera, normalize_source
from app.services.camera.manager import camera_manager, warmup_camera_permissions
from app.services.camera.registry import new_camera_id, serialize_camera, spec_from_row

router = APIRouter(prefix="/cameras", tags=["cameras"], dependencies=[Depends(current_user)])

CameraType = Literal["webcam", "rtsp", "http", "file"]

# Pause between stream polls so an idle/slow stream doesn't spin the loop.
STREAM_POLL_INTERVAL = 0.03


class CameraCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: CameraType
    source: str = Field(min_length=1, max_length=500)
    enabled: bool = True


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    type: CameraType | None = None
    source: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool | None = None


class SourceTest(BaseModel):
    type: CameraType
    source: str = Field(min_length=1, max_length=500)


def _normalized_or_422(camera_type: str, source: str) -> str:
    try:
        return normalize_source(camera_type, source)
    except SourceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _name_taken(session, name: str, exclude_id: str | None = None) -> bool:
    stmt = select(func.count()).select_from(Camera).where(func.lower(Camera.name) == name.lower())
    if exclude_id:
        stmt = stmt.where(Camera.id != exclude_id)
    return bool(session.scalar(stmt))


def _get_camera_or_404(session, camera_id: str) -> Camera:
    row = session.get(Camera, camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Camera '{camera_id}' not found")
    return row


def _for_user(camera: dict, user: AuthUser) -> dict:
    """Only administrators get the raw source (RTSP/HTTP URLs can contain a
    password); everyone else sees the masked `source_display` only."""
    return camera if user.is_admin else {**camera, "source": camera["source_display"]}


@router.get("")
def list_cameras(user: AuthUser = Depends(current_user)):
    with SessionLocal() as session:
        rows = session.scalars(select(Camera).order_by(Camera.created_at, Camera.id)).all()
        return [_for_user(serialize_camera(r), user) for r in rows]


@router.post("/test", dependencies=[Depends(require_admin)])
def test_camera_source(body: SourceTest):
    """Try to open a source and grab one frame, without saving anything."""
    try:
        source = normalize_source(body.type, body.source)
    except SourceError as exc:
        return {"ok": False, "error": str(exc)}

    camera = build_camera(CameraSpec(id="test", name="test", type=body.type, source=source))
    try:
        if not camera.open():
            hint = (
                " Check macOS camera permission and that no other app is using it."
                if body.type == "webcam"
                else " Check the address, credentials and that the camera is reachable."
            )
            return {"ok": False, "error": "Could not open this source." + hint}
        ok, frame = camera.read()
        if not ok or frame is None:
            return {"ok": False, "error": "Opened the source but could not read a frame from it."}
        height, width = frame.shape[:2]
        return {"ok": True, "width": width, "height": height}
    except Exception as exc:
        return {"ok": False, "error": f"Unexpected error: {exc}"}
    finally:
        camera.release()


@router.post("", status_code=201, dependencies=[Depends(require_admin)])
async def create_camera(body: CameraCreate):
    # `async def` on purpose: uvicorn's event loop runs on the process's main
    # thread, which is where macOS must show the camera-permission prompt.
    name = body.name.strip()
    source = _normalized_or_422(body.type, body.source)

    with SessionLocal() as session:
        if _name_taken(session, name):
            raise HTTPException(status_code=409, detail=f"A camera named '{name}' already exists")
        row = Camera(id=new_camera_id(name), name=name, type=body.type, source=source, enabled=body.enabled)
        session.add(row)
        session.commit()
        spec = spec_from_row(row)

    if body.enabled:
        warmup_camera_permissions([spec])
        camera_manager.start_camera(spec)

    with SessionLocal() as session:
        return serialize_camera(session.get(Camera, spec.id))


@router.get("/{camera_id}")
def get_camera(camera_id: str, user: AuthUser = Depends(current_user)):
    with SessionLocal() as session:
        return _for_user(serialize_camera(_get_camera_or_404(session, camera_id)), user)


@router.patch("/{camera_id}", dependencies=[Depends(require_admin)])
async def update_camera(camera_id: str, body: CameraUpdate):
    with SessionLocal() as session:
        row = _get_camera_or_404(session, camera_id)

        new_name = body.name.strip() if body.name is not None else row.name
        new_type = body.type if body.type is not None else row.type
        new_enabled = body.enabled if body.enabled is not None else row.enabled
        raw_source = body.source if body.source is not None else row.source
        new_source = _normalized_or_422(new_type, raw_source)

        if new_name != row.name and _name_taken(session, new_name, exclude_id=camera_id):
            raise HTTPException(status_code=409, detail=f"A camera named '{new_name}' already exists")

        needs_restart = (new_type, new_source, new_enabled) != (row.type, row.source, row.enabled)
        renamed = new_name != row.name

        row.name, row.type, row.source, row.enabled = new_name, new_type, new_source, new_enabled
        session.commit()
        spec = spec_from_row(row)

    if needs_restart:
        await run_in_threadpool(camera_manager.stop_camera, camera_id, resolve_alerts=True)
        if new_enabled:
            warmup_camera_permissions([spec])
            camera_manager.start_camera(spec)
    elif renamed:
        camera_manager.rename(camera_id, new_name)

    with SessionLocal() as session:
        return serialize_camera(session.get(Camera, camera_id))


@router.delete("/{camera_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_camera(camera_id: str):
    """Remove a camera. Its past events and recordings are kept."""
    with SessionLocal() as session:
        _get_camera_or_404(session, camera_id)
    camera_manager.stop_camera(camera_id, resolve_alerts=True)
    with SessionLocal() as session:
        session.delete(session.get(Camera, camera_id))
        session.execute(delete(Zone).where(Zone.camera_id == camera_id))  # its rules go with it
        session.execute(delete(CameraRules).where(CameraRules.camera_id == camera_id))
        session.commit()
    return Response(status_code=204)


async def _mjpeg_generator(camera_id: str):
    # Async (not a sync generator) so each viewer costs no threadpool thread
    # and a closed browser tab cancels the stream immediately.
    last_sent: bytes | None = None
    while not shutdown_event.is_set():
        worker = camera_manager.get(camera_id)
        if worker is None:
            break
        frame = worker.get_latest_jpeg()
        if frame is not None and frame is not last_sent:
            last_sent = frame
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        await asyncio.sleep(STREAM_POLL_INTERVAL)


@router.get("/{camera_id}/stream")
def camera_stream(camera_id: str):
    if camera_manager.get(camera_id) is None:
        raise HTTPException(status_code=404, detail="Camera is not running")
    return StreamingResponse(
        _mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{camera_id}/snapshot")
def camera_snapshot(camera_id: str):
    """Latest frame as a single JPEG (cheap alternative to a live stream)."""
    worker = camera_manager.get(camera_id)
    frame = worker.get_latest_jpeg() if worker else None
    if frame is None:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(content=frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
