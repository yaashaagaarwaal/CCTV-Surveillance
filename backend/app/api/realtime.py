import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.shutdown import shutdown_event
from app.security.deps import websocket_user
from app.services.alert_bus import alert_bus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["realtime"])

HEARTBEAT_SECONDS = 25


@router.websocket("/alerts")
async def alerts_socket(websocket: WebSocket):
    """Live alert feed. Requires the same login cookie as the rest of the API
    (browsers send it on the handshake); the Origin check happens in middleware."""
    user = await asyncio.to_thread(websocket_user, websocket)  # DB lookup off the event loop
    if user is None:
        await websocket.close(code=1008)  # policy violation: not authenticated
        return

    await websocket.accept()
    queue = alert_bus.subscribe()
    logger.info("Alert socket opened for %r (%d connected)", user.username, alert_bus.subscriber_count)
    last_ping = time.monotonic()
    try:
        # Poll the queue once a second so the loop also notices server shutdown.
        while not shutdown_event.is_set():
            try:
                await websocket.send_json(await asyncio.wait_for(queue.get(), timeout=1.0))
            except asyncio.TimeoutError:
                if time.monotonic() - last_ping >= HEARTBEAT_SECONDS:
                    await websocket.send_json({"type": "ping"})  # lets the browser notice dead connections
                    last_ping = time.monotonic()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        alert_bus.unsubscribe(queue)
        logger.info("Alert socket closed for %r", user.username)
