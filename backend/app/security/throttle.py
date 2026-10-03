import threading
import time

from app.core.config import settings


class LoginThrottle:
    """Slows down password guessing. After N failures for the same
    (client address, username) the pair is locked out for a while; a looser
    limit applies to a client address overall, so rotating usernames doesn't
    help. In memory only: restarting the server clears it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[tuple[str, str], list[float]] = {}

    def _recent(self, key: tuple[str, str], now: float) -> list[float]:
        window = settings.security.login_lockout_seconds
        recent = [t for t in self._failures.get(key, []) if now - t < window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def retry_after(self, ip: str, username: str) -> int:
        """Seconds the caller must wait (0 = allowed)."""
        now = time.monotonic()
        limit = settings.security.login_max_failures
        with self._lock:
            waits = []
            for key, max_failures in (((ip, username), limit), ((ip, "*"), limit * 4)):
                recent = self._recent(key, now)
                if len(recent) >= max_failures:
                    waits.append(int(settings.security.login_lockout_seconds - (now - recent[0])) + 1)
            return max(waits, default=0)

    def failed(self, ip: str, username: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in ((ip, username), (ip, "*")):
                self._failures.setdefault(key, []).append(now)

    def succeeded(self, ip: str, username: str) -> None:
        with self._lock:
            self._failures.pop((ip, username), None)


login_throttle = LoginThrottle()
