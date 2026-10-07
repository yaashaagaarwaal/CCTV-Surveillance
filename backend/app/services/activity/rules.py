from dataclasses import dataclass

from app.core.config import settings
from app.db.models import CameraRules
from app.db.session import SessionLocal


@dataclass(frozen=True)
class RulesSpec:
    """A camera's security hours and fall-detection switch."""

    quiet_start: str | None = None
    quiet_end: str | None = None
    fall_enabled: bool = False

    @property
    def has_quiet_hours(self) -> bool:
        return bool(self.quiet_start and self.quiet_end)


def default_rules() -> RulesSpec:
    cfg = settings.activity
    if cfg.after_hours_enabled:
        return RulesSpec(cfg.after_hours_start, cfg.after_hours_end)
    return RulesSpec()


def load_rules(camera_id: str) -> RulesSpec:
    """The camera's saved rules, or the server-wide defaults if it has none."""
    with SessionLocal() as db:
        row = db.get(CameraRules, camera_id)
        if row is None:
            return default_rules()
        return RulesSpec(row.quiet_start, row.quiet_end, bool(row.fall_detection))
