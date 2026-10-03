import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class AlertBus:
    """Fans alert messages out to connected WebSocket clients.

    Alerts are raised on camera worker threads, but WebSockets live on the
    asyncio event loop, so `publish` is thread-safe: it hands the message to
    the loop with call_soon_threadsafe. Each subscriber has a small bounded
    queue; a client that can't keep up just misses messages (it refetches the
    alert list on the next one anyway).
    """

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue] = set()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, message: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fan_out, message)
        except RuntimeError:  # loop shutting down
            logger.debug("Alert bus: event loop closed, message dropped")

    def _fan_out(self, message: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                pass


alert_bus = AlertBus()
