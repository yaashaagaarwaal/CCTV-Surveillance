import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.services.camera.manager import camera_manager

router = APIRouter(prefix="/cameras", tags=["cameras"])

# Small sleep between stream reads so a client that briefly falls behind (or
# a camera between frames) doesn't spin the loop at 100% CPU.
STREAM_POLL_INTERVAL = 0.03


def _get_worker_or_404(camera_id: str):
    worker = camera_manager.get(camera_id)
    if worker is None:
        raise HTTPException(status_code=404, detail=f"Unknown camera '{camera_id}'")
    return worker


@router.get("")
def list_cameras():
    return camera_manager.list_status()


@router.get("/{camera_id}/status")
def camera_status(camera_id: str):
    worker = _get_worker_or_404(camera_id)
    detections = worker.get_live_detections()
    return {
        "id": worker.camera_id,
        "name": worker.camera.name,
        "status": worker.get_status().value,
        "people_detected": len(detections),
        "detections": [{"confidence": d.confidence, "bbox": d.bbox} for d in detections],
    }


def _mjpeg_generator(camera_id: str):
    last_sent: bytes | None = None
    while True:
        worker = camera_manager.get(camera_id)
        if worker is None:
            break
        frame = worker.get_latest_jpeg()
        if frame is not None and frame is not last_sent:
            last_sent = frame
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(STREAM_POLL_INTERVAL)


@router.get("/{camera_id}/stream")
def camera_stream(camera_id: str):
    _get_worker_or_404(camera_id)
    return StreamingResponse(
        _mjpeg_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
