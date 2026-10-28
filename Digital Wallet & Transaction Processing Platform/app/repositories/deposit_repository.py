from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Deposit


class DepositRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, deposit_id: int, *, lock: bool = False) -> Deposit | None:
        query = select(Deposit).where(Deposit.id == deposit_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> list[Deposit]:
        query = select(Deposit).where(Deposit.user_id == user_id).order_by(Deposit.created_at.desc())
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def list(self, *, user_id: int | None = None, page: int = 1, page_size: int = 20) -> list[Deposit]:
        query = select(Deposit).order_by(Deposit.created_at.desc())
        if user_id is not None:
            query = query.where(Deposit.user_id == user_id)
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))
