"""Counting people from a standard person detector, honestly.

YOLO returns one box per person it can see. Two things make a box count different from the
number of people, and this module deals with the first and reports the second:

  * DUPLICATES (fixed here): the detector sometimes draws two boxes round one person (a tall one and
    a shorter one inside it). Counting both would invent a person, so boxes that are mostly inside a
    stronger box, or overlap it almost entirely, are merged into one.
  * OCCLUSION (cannot be fixed, so it is flagged): people standing in front of each other are hidden
    or merged, so the count is a LOWER BOUND. Heavily overlapping boxes, or a large count, mark the
    result `approximate`, and alerts say "at least N".

No tracking IDs are needed to avoid double counting inside one frame: it is one box per person per
frame. What a count can never do is tell how many people are in a dense crowd.
"""
from dataclasses import dataclass

from app.services.activity.zones import ZoneSpec
from app.services.detection.detector import Detection

DUPLICATE_IOU = 0.65  # two boxes overlapping this much (intersection over union) are one person
DUPLICATE_CONTAINMENT = 0.85  # a box this much inside another (intersection over the smaller box) is one person
OVERLAP_IOU = 0.10  # people overlapping this much are partly hiding each other: the count may be low
APPROXIMATE_FROM = 2  # from two people on, someone may be hidden behind someone: the count is "at least" (scripts/crowd_benchmark.py)


def _area(box) -> float:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def _intersection(a, b) -> float:
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def iou(a, b) -> float:
    inter = _intersection(a, b)
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def containment(a, b) -> float:
    """How much of the smaller box lies inside the other (1.0 = entirely inside)."""
    smaller = min(_area(a), _area(b))
    return _intersection(a, b) / smaller if smaller > 0 else 0.0


def unique_people(detections: list[Detection]) -> list[Detection]:
    """One box per person: a weaker box that duplicates a stronger one is dropped."""
    kept: list[Detection] = []
    for candidate in sorted(detections, key=lambda d: -d.confidence):
        if any(iou(candidate.bbox, k.bbox) >= DUPLICATE_IOU or containment(candidate.bbox, k.bbox) >= DUPLICATE_CONTAINMENT for k in kept):
            continue
        kept.append(candidate)
    return kept


def partly_hidden(detections: list[Detection]) -> bool:
    """Do any two people overlap enough that one may be hiding the other?"""
    return any(iou(a.bbox, b.bbox) >= OVERLAP_IOU for i, a in enumerate(detections) for b in detections[i + 1 :])


@dataclass(frozen=True)
class CrowdCount:
    count: int
    approximate: bool  # True: at least this many (overlap or a large group)
    region: str | None  # zone name, or None for the whole picture

    def as_dict(self) -> dict:
        return {"count": self.count, "approximate": self.approximate, "region": self.region}


def count_people(detections: list[Detection], zone: ZoneSpec | None, width: int, height: int) -> CrowdCount:
    """Distinct people in the picture, or standing (feet) inside `zone`."""
    people = unique_people(detections)
    if zone is not None:
        people = [d for d in people if zone.contains((d.bbox[0] + d.bbox[2]) / 2, d.bbox[3], width, height)]
    return CrowdCount(len(people), partly_hidden(people) or len(people) >= APPROXIMATE_FROM, zone.name if zone else None)


@dataclass
class CrowdTimer:
    """How long the count has stayed at or above the limit.

    A detector flickers: one missed person for a cycle or two would reset a naive timer, so a dip
    shorter than `grace` seconds does not restart it. A dip longer than that, or a gap with no
    detection cycles at all (no motion, camera outage), does: the crowd is then treated as gone.
    """

    over_since: float | None = None
    last_over: float | None = None
    alerted: bool = False  # one alert per crowded episode

    def update(self, over: bool, now: float, grace: float) -> float:
        """Feed one detection cycle. Returns seconds the episode has lasted (0 when there is none)."""
        if self.last_over is not None and now - self.last_over > grace:
            self.reset()  # too long since we last saw a crowd, however it ended
        if over:
            if self.over_since is None:
                self.over_since = now
            self.last_over = now
        if self.over_since is None:
            return 0.0
        return now - self.over_since

    def reset(self) -> None:
        self.over_since, self.last_over, self.alerted = None, None, False
