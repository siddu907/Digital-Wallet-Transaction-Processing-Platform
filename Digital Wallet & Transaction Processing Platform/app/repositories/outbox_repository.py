from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OutboxEvent


class OutboxRepository:
    def __init__(self, session: Session):
        self.session = session

    def enqueue(self, event: OutboxEvent) -> OutboxEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def pending(self, limit: int = 100) -> list[OutboxEvent]:
        query = (
            select(OutboxEvent)
            .where(OutboxEvent.processed_at.is_(None))
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(query))
