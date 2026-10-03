from app.db.models import Event

# An event is as severe as the most serious thing seen during its recording:
# a "person" event that later contains an unknown face becomes "unknown_person",
# but a later plain person sighting never downgrades it back.
EVENT_TYPE_RANK = {"motion": 0, "person": 1, "suspicious_activity": 2, "unknown_person": 3, "restricted_area": 4}


def upgrade_event_type(event: Event, new_type: str) -> None:
    if EVENT_TYPE_RANK.get(new_type, 0) > EVENT_TYPE_RANK.get(event.event_type, 0):
        event.event_type = new_type
