from app.models import OutboxEvent


def enqueue(db, event_type: str, aggregate_id: int, payload: dict):
    event = OutboxEvent(event_type=event_type, aggregate_id=aggregate_id, payload=payload)
    db.add(event)
    return event


__all__ = ["enqueue"]
