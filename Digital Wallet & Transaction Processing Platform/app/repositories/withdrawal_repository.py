from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Withdrawal


class WithdrawalRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, withdrawal_id: int, *, lock: bool = False) -> Withdrawal | None:
        query = select(Withdrawal).where(Withdrawal.id == withdrawal_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> list[Withdrawal]:
        query = select(Withdrawal).where(Withdrawal.user_id == user_id).order_by(Withdrawal.created_at.desc())
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def list(self, *, user_id: int | None = None, page: int = 1, page_size: int = 20) -> list[Withdrawal]:
        query = select(Withdrawal).order_by(Withdrawal.created_at.desc())
        if user_id is not None:
            query = query.where(Withdrawal.user_id == user_id)
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))
