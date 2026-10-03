from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.security.deps import current_user, require_admin
from app.services.notifications.dispatcher import dispatcher
from app.services.notifications.email import EmailChannel

router = APIRouter(prefix="/notifications", tags=["notifications"], dependencies=[Depends(current_user)])


@router.get("/status")
def notification_status():
    cfg = settings.email
    active = [c.name for c in dispatcher.channels]
    return {
        "email": {
            "enabled": cfg.enabled,
            "active": "email" in active,
            "configured": bool(cfg.host and cfg.to_addrs),
            "min_severity": cfg.min_severity,
            "recipients": len(cfg.to_addrs),
        },
        "channels": active,
    }


@router.post("/test-email", dependencies=[Depends(require_admin)])
def send_test_email():
    channel = next((c for c in dispatcher.channels if isinstance(c, EmailChannel)), None)
    if channel is None:
        raise HTTPException(status_code=409, detail="Email notifications are not enabled/configured (see .env.example)")
    try:
        channel.send_test()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not send: {exc}") from exc
    return {"sent": True, "recipients": len(channel.config.to_addrs)}
