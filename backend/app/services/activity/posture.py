from dataclasses import dataclass

from app.core.config import ActivityConfig


@dataclass
class FallEvent:
    """What the heuristic saw, for the alert's explanation."""

    change_seconds: float  # how fast the person went from upright to lying
    down_seconds: float  # how long they have stayed down
    height_drop: float  # fraction by which the box got shorter


@dataclass
class PostureState:
    """Fall-like posture change for ONE tracked person, from bounding boxes only.

    The rule: the box was upright (tall and narrow), then within a few seconds
    became wide and clearly shorter, with its centre dropping, and it stays that
    way for a while. A person first seen already lying (asleep on a sofa) never
    triggers it, because the sudden change was never observed.

    This is a heuristic on a rectangle, not pose estimation. It can miss falls
    (partly hidden, seen from above or end-on) and can fire on someone who lies
    down quickly on purpose. Treat it as "worth a look", not as a diagnosis.
    """

    upright: tuple[float, float, float] | None = None  # (time, box height, box centre y) last seen standing
    down_since: float | None = None
    change_seconds: float = 0.0
    height_drop: float = 0.0
    alerted: bool = False

    def update(self, width: float, height: float, centre_y: float, now: float, frame_height: int, cfg: ActivityConfig) -> FallEvent | None:
        """Feed this person's box for the current cycle. Returns a FallEvent once
        (when a fall-like change has been confirmed), else None."""
        ratio = height / max(width, 1.0)

        if ratio >= cfg.fall_upright_ratio:
            if height >= cfg.fall_min_person_height * frame_height:
                self.upright = (now, height, centre_y)
            self.down_since, self.alerted = None, False
            return None

        if self.down_since is None:
            if self.upright is None or ratio > cfg.fall_lying_ratio:
                return None
            seen_at, upright_height, upright_centre = self.upright
            quick = now - seen_at <= cfg.fall_window_seconds
            shorter = height <= (1.0 - cfg.fall_min_height_drop) * upright_height
            lower = centre_y >= upright_centre + 0.1 * upright_height
            if quick and shorter and lower:
                self.down_since = now
                self.change_seconds = now - seen_at
                self.height_drop = 1.0 - height / upright_height
            return None

        if ratio >= cfg.fall_recovered_ratio:
            self.down_since, self.alerted = None, False  # got back up
            return None
        if not self.alerted and now - self.down_since >= cfg.fall_confirm_seconds:
            self.alerted = True
            return FallEvent(self.change_seconds, now - self.down_since, self.height_drop)
        return None
