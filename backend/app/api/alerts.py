from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update

from app.db.models import Alert, Event
from app.db.session import SessionLocal
from app.security.deps import current_user, require_admin
from app.security.sessions import AuthUser
from app.services.alert_bus import alert_bus
from app.services.alerts import ALERT_TYPES, SEVERITIES, serialize_alert
from app.services.faces.storage import resolve

# Viewers can read and resolve alerts; deleting them is admin-only.
router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(current_user)])


def _get_or_404(session, alert_id: int) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return alert


@router.get("")
def list_alerts(
    state: str = Query("all", pattern="^(open|resolved|all)$"),
    unread: bool | None = None,
    alert_type: str | None = Query(None, alias="type"),
    severity: str | None = None,
    camera_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Newest first. `state=open` = not yet resolved; `unread=true` = not yet marked read."""
    if alert_type and alert_type not in ALERT_TYPES:
        raise HTTPException(status_code=422, detail=f"type must be one of {', '.join(ALERT_TYPES)}")
    if severity and severity not in SEVERITIES:
        raise HTTPException(status_code=422, detail=f"severity must be one of {', '.join(SEVERITIES)}")

    conditions = []
    if state == "open":
        conditions.append(Alert.resolved_at.is_(None))
    elif state == "resolved":
        conditions.append(Alert.resolved_at.is_not(None))
    if unread is True:
        conditions.append(Alert.acknowledged_at.is_(None))
    elif unread is False:
        conditions.append(Alert.acknowledged_at.is_not(None))
    if alert_type:
        conditions.append(Alert.type == alert_type)
    if severity:
        conditions.append(Alert.severity == severity)
    if camera_id:
        conditions.append(Alert.camera_id == camera_id)

    with SessionLocal() as session:
        count = lambda *c: session.scalar(select(func.count()).select_from(Alert).where(*c)) or 0  # noqa: E731
        alerts = session.scalars(
            select(Alert).where(*conditions).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit).offset(offset)
        ).all()
        event_ids = [a.event_id for a in alerts if a.event_id]
        existing = set(session.scalars(select(Event.id).where(Event.id.in_(event_ids)))) if event_ids else set()
        return {
            "items": [serialize_alert(a, a.event_id in existing) for a in alerts],
            "total": count(*conditions),
            "unread": count(Alert.resolved_at.is_(None), Alert.acknowledged_at.is_(None)),  # drives the bell badge
            "open": count(Alert.resolved_at.is_(None)),
        }


@router.post("/read-all")
def mark_all_read():
    with SessionLocal() as session:
        result = session.execute(
            update(Alert).where(Alert.acknowledged_at.is_(None)).values(acknowledged_at=datetime.now(timezone.utc))
        )
        session.commit()
    alert_bus.publish({"type": "alert_updated", "ids": []})
    return {"marked_read": result.rowcount}


@router.post("/{alert_id}/read")
def mark_read(alert_id: int):
    with SessionLocal() as session:
        alert = _get_or_404(session, alert_id)
        if alert.acknowledged_at is None:
            alert.acknowledged_at = datetime.now(timezone.utc)
            session.commit()
        result = serialize_alert(alert)
    alert_bus.publish({"type": "alert_updated", "ids": [alert_id]})
    return result


@router.post("/{alert_id}/resolve")
def resolve_alert(alert_id: int, user: AuthUser = Depends(current_user)):
    """Mark an alert as dealt with (also marks it read)."""
    with SessionLocal() as session:
        alert = _get_or_404(session, alert_id)
        if alert.resolved_at is None:
            now = datetime.now(timezone.utc)
            alert.resolved_at, alert.resolved_by = now, user.username
            alert.acknowledged_at = alert.acknowledged_at or now
            session.commit()
        result = serialize_alert(alert)
    alert_bus.publish({"type": "alert_updated", "ids": [alert_id]})
    return result


@router.get("/{alert_id}/snapshot")
def alert_snapshot(alert_id: int):
    with SessionLocal() as session:
        relative = _get_or_404(session, alert_id).snapshot_path
    if not relative or not resolve(relative).is_file():
        raise HTTPException(status_code=404, detail="No snapshot for this alert")
    return FileResponse(resolve(relative), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{alert_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_alert(alert_id: int):
    with SessionLocal() as session:
        alert = _get_or_404(session, alert_id)
        if alert.snapshot_path:
            resolve(alert.snapshot_path).unlink(missing_ok=True)
        session.delete(alert)
        session.commit()
    alert_bus.publish({"type": "alert_updated", "ids": [alert_id]})
    return Response(status_code=204)
