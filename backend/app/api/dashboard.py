from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.api.events import PLAYABLE_STATUSES
from app.db.models import Alert, Camera, Event
from app.db.session import SessionLocal
from app.security.deps import current_user
from app.services.camera.registry import serialize_camera

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(current_user)])


def _start_of_local_day_utc() -> datetime:
    """Midnight of the server's local day, as a naive UTC datetime (the form
    timestamps are stored in)."""
    local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/summary")
def dashboard_summary():
    """Everything the dashboard header needs in a single request."""
    day_start = _start_of_local_day_utc()

    with SessionLocal() as session:
        cameras = [serialize_camera(row) for row in session.scalars(select(Camera).order_by(Camera.created_at))]

        def count_events(*conditions) -> int:
            return session.scalar(select(func.count()).select_from(Event).where(*conditions)) or 0

        unread_alerts = session.scalar(select(func.count()).select_from(Alert).where(Alert.resolved_at.is_(None), Alert.acknowledged_at.is_(None))) or 0
        open_alerts = session.scalar(select(func.count()).select_from(Alert).where(Alert.resolved_at.is_(None))) or 0
        events_today = count_events(Event.timestamp >= day_start)
        person_events_today = count_events(Event.timestamp >= day_start, Event.event_type == "person")
        recordings_today = count_events(
            Event.timestamp >= day_start,
            Event.recording_path.is_not(None),
            Event.status.in_(PLAYABLE_STATUSES),
        )

    enabled = [c for c in cameras if c["enabled"]]
    alerts = []
    for cam in enabled:
        if cam["status"] == "online" and cam["people_detected"] > 0:
            best = max(d["confidence"] for d in cam["detections"])
            n = cam["people_detected"]
            names = sorted({f["name"] for f in cam["faces"] if f["label"] == "known"})
            unknown = sum(f["label"] == "unknown" for f in cam["faces"])
            detail = ", ".join(names + ([f"{unknown} unknown"] if unknown else []))
            alerts.append(
                {
                    "id": f"person-{cam['id']}",
                    "type": "person_detected",
                    "severity": "high",
                    "camera_id": cam["id"],
                    "camera_name": cam["name"],
                    "message": f"{n} {'person' if n == 1 else 'people'} detected" + (f" ({detail})" if detail else ""),
                    "confidence": best,
                }
            )

    return {
        "cameras": {
            "total": len(cameras),
            "enabled": len(enabled),
            "online": sum(c["status"] == "online" for c in enabled),
            "offline": sum(c["status"] == "offline" for c in enabled),
        },
        "people_now": sum(c["people_detected"] for c in enabled),
        "active_recordings": sum(c["recording"] for c in enabled),
        "events_today": events_today,
        "person_events_today": person_events_today,
        "recordings_today": recordings_today,
        "unread_alerts": unread_alerts,
        "open_alerts": open_alerts,
        "night_cameras": sum(bool(c["lighting"] and c["lighting"]["night"]) for c in enabled if c["status"] == "online"),
        "alerts": alerts,
    }
