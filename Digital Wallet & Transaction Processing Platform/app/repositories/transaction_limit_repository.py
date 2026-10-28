from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TransactionLimit


class TransactionLimitRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_current(self, *, lock: bool = False) -> TransactionLimit | None:
        query = select(TransactionLimit).where(TransactionLimit.id == 1)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)
