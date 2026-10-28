from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: int, key: str, *, lock: bool = False) -> IdempotencyKey | None:
        query = select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.key == key,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def add(self, record: IdempotencyKey) -> IdempotencyKey:
        self.session.add(record)
        self.session.flush()
        return record
