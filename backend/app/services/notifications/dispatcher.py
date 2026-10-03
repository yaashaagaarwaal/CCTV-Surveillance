import logging
import queue
import threading
import time

from app.core.config import settings
from app.services.notifications.base import NotificationChannel
from app.services.notifications.email import EmailChannel

logger = logging.getLogger(__name__)


def build_channels() -> list[NotificationChannel]:
    """Channels enabled by configuration. Add new channels here."""
    channels: list[NotificationChannel] = []
    cfg = settings.email
    if cfg.enabled:
        if cfg.host and cfg.to_addrs:
            channels.append(EmailChannel(cfg))
        else:
            logger.warning("Email notifications are enabled but EMAIL__HOST / EMAIL__TO_ADDRS are not set; skipping")
    return channels


class NotificationDispatcher:
    """Sends alerts to notification channels on a background thread, so a slow
    or unreachable mail server can never stall a camera thread or the API.
    Failures are logged and (once) retried — they never propagate."""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=200)
        self._channels: list[NotificationChannel] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def channels(self) -> list[NotificationChannel]:
        return self._channels

    def start(self) -> None:
        self._channels = build_channels()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="notifications")
        self._thread.start()
        logger.info("Notification channels: %s", [c.name for c in self._channels] or "none")

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)

    def dispatch(self, alert: dict, snapshot_path: str | None) -> None:
        if not self._channels:
            return
        try:
            self._queue.put_nowait((alert, snapshot_path))
        except queue.Full:
            logger.warning("Notification queue full; dropping notification for alert #%s", alert.get("id"))

    def _run(self) -> None:
        while not self._stop.is_set():
            item = self._queue.get()
            if item is None:
                break
            alert, snapshot_path = item
            for channel in self._channels:
                if not channel.wants(alert):
                    continue
                for attempt in (1, 2):
                    try:
                        channel.send(alert, snapshot_path)
                        break
                    except Exception:
                        logger.exception("%s notification failed for alert #%s (attempt %d)", channel.name, alert.get("id"), attempt)
                        if attempt == 1 and not self._stop.wait(3):
                            continue
                        break


dispatcher = NotificationDispatcher()
