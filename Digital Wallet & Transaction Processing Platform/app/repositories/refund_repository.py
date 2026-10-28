from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Refund, RefundStatus


class RefundRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, refund_id: int, *, lock: bool = False) -> Refund | None:
        query = select(Refund).where(Refund.id == refund_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> list[Refund]:
        query = select(Refund).where(Refund.user_id == user_id).order_by(Refund.created_at.desc())
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def list(self, *, user_id: int | None = None, page: int = 1, page_size: int = 20) -> list[Refund]:
        query = select(Refund).order_by(Refund.created_at.desc())
        if user_id is not None:
            query = query.where(Refund.user_id == user_id)
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def total_for_ledger(self, ledger_entry_id: int, statuses: list) -> object:
        return self.session.scalar(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.ledger_entry_id == ledger_entry_id,
                Refund.status.in_(statuses),
            )
        )

    def approved_for_processing(self, limit: int = 100) -> list[Refund]:
        query = (
            select(Refund)
            .where(Refund.status == RefundStatus.APPROVED)
            .order_by(Refund.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(query))
