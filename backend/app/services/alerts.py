import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models import Alert, Camera, Event
from app.db.session import SessionLocal
from app.services.alert_bus import alert_bus
from app.services.faces.storage import resolve

logger = logging.getLogger(__name__)

ALERT_TYPES = ("unknown_person", "restricted_area", "suspicious_activity", "camera_offline")
SEVERITIES = ("low", "medium", "high", "critical")
SEVERITY_RANK = {name: rank for rank, name in enumerate(SEVERITIES)}


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def serialize_alert(alert: Alert, event_available: bool = False) -> dict:
    return {
        "id": alert.id,
        "type": alert.type,
        "severity": alert.severity,
        "camera_id": alert.camera_id,
        "event_id": alert.event_id,
        "event_available": event_available,
        "message": alert.message,
        "details": json.loads(alert.details) if alert.details else {},
        "occurrences": alert.occurrences or 1,
        "has_snapshot": bool(alert.snapshot_path) and resolve(alert.snapshot_path).is_file(),
        "created_at": iso_utc(alert.created_at),
        "read": alert.acknowledged_at is not None,
        "read_at": iso_utc(alert.acknowledged_at),
        "resolved": alert.resolved_at is not None,
        "resolved_at": iso_utc(alert.resolved_at),
        "resolved_by": alert.resolved_by,
    }


def raise_alert(
    *,
    alert_type: str,
    severity: str,
    camera_id: str,
    message: str,
    event_id: int | None = None,
    snapshot_path: str | None = None,
    details: dict | None = None,
    dedupe_key: str | None = None,
) -> int:
    """Create an alert, push it to connected dashboards and notify channels.

    If `dedupe_key` matches an alert that is still open (unresolved), no new
    alert is created — its `occurrences` counter goes up instead — so one
    ongoing condition produces one alert. Returns the alert id.

    This is the single place alerts are created, which is what makes adding a
    notification channel (email today; push, webhook, ...) a local change.
    """
    from app.services.notifications.dispatcher import dispatcher  # avoid import cycle at module load

    if severity not in SEVERITY_RANK:
        raise ValueError(f"Unknown severity '{severity}'")

    with SessionLocal() as session:
        if dedupe_key:
            existing = session.scalar(
                select(Alert).where(Alert.dedupe_key == dedupe_key, Alert.resolved_at.is_(None)).limit(1)
            )
            if existing is not None:
                existing.occurrences = (existing.occurrences or 1) + 1
                session.commit()
                return existing.id

        alert = Alert(
            type=alert_type,
            severity=severity,
            camera_id=camera_id,
            event_id=event_id,
            message=message,
            snapshot_path=snapshot_path,
            details=json.dumps(details) if details else None,
            dedupe_key=dedupe_key,
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        payload = serialize_alert(alert, event_available=event_id is not None)
        camera = session.get(Camera, camera_id)
        payload["camera_name"] = camera.name if camera else camera_id
        snapshot_rel = alert.snapshot_path

    logger.warning("ALERT #%s [%s/%s] camera=%s: %s", payload["id"], alert_type, severity, camera_id, message)
    alert_bus.publish({"type": "alert_created", "alert": payload})
    dispatcher.dispatch(payload, snapshot_rel)
    return payload["id"]


def resolve_by_key(dedupe_key: str, resolved_by: str = "system") -> int:
    """Resolve every open alert with this key (e.g. camera back online)."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        open_alerts = session.scalars(
            select(Alert).where(Alert.dedupe_key == dedupe_key, Alert.resolved_at.is_(None))
        ).all()
        for alert in open_alerts:
            alert.resolved_at = now
            alert.resolved_by = resolved_by
            if alert.acknowledged_at is None:
                alert.acknowledged_at = now  # nobody needs to read an alert that no longer applies
        session.commit()
        ids = [a.id for a in open_alerts]
    if ids:
        logger.info("Resolved %d alert(s) for %s (%s)", len(ids), dedupe_key, resolved_by)
        alert_bus.publish({"type": "alert_updated", "ids": ids})
    return len(ids)
