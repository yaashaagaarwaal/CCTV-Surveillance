from abc import ABC, abstractmethod


class NotificationChannel(ABC):
    """One way of telling a person about an alert (email, push, webhook...).

    To add a channel: subclass this, implement `send`, and register it in
    `build_channels()` (dispatcher.py). `send` runs on a background thread, so
    it may block; raising is fine — the dispatcher logs it and moves on.
    """

    name: str = "channel"

    @abstractmethod
    def wants(self, alert: dict) -> bool:
        """Whether this channel should be used for this alert (severity filter, ...)."""

    @abstractmethod
    def send(self, alert: dict, snapshot_path: str | None) -> None:
        """Deliver the alert. `alert` is the serialized alert plus `camera_name`."""
