from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Deposit,
    OperationStatus,
    Refund,
    RefundStatus,
    RiskStatus,
    SuspiciousTransaction,
    Transfer,
    Withdrawal,
)


class SuspiciousTransactionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(
        self,
        suspicious_id: int,
        *,
        lock: bool = False,
        refresh: bool = False,
    ) -> SuspiciousTransaction | None:
        query = select(SuspiciousTransaction).where(SuspiciousTransaction.id == suspicious_id)
        if lock:
            query = query.with_for_update()
        if refresh:
            query = query.execution_options(populate_existing=True)
        return self.session.scalar(query)

    def for_operation(
        self,
        operation_type: str,
        operation_id: int,
        *,
        lock: bool = False,
    ) -> SuspiciousTransaction | None:
        query = select(SuspiciousTransaction).where(
            SuspiciousTransaction.operation_type == operation_type,
            SuspiciousTransaction.operation_id == operation_id,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def pending_reviews(self) -> list[SuspiciousTransaction]:
        query = select(SuspiciousTransaction).where(
            SuspiciousTransaction.status == RiskStatus.REVIEW_REQUIRED
        ).order_by(SuspiciousTransaction.created_at.asc())
        return list(self.session.scalars(query))

    def list(self, *, page: int = 1, page_size: int = 20) -> list[SuspiciousTransaction]:
        query = select(SuspiciousTransaction).order_by(SuspiciousTransaction.created_at.desc())
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def activity_counts(
        self,
        user_id: int,
        start: datetime,
        end: datetime | None = None,
    ) -> tuple[int, int]:
        transfer_count = 0
        total_count = 0
        for model in (Deposit, Transfer, Withdrawal, Refund):
            predicates = [model.user_id == user_id, model.created_at >= start]
            if end is not None:
                predicates.append(model.created_at <= end)
            count = self.session.scalar(
                select(func.count()).select_from(model).where(*predicates)
            ) or 0
            total_count += count
            if model is Transfer:
                transfer_count = count
        return transfer_count, total_count

    def completed_transfers(self, limit: int = 500) -> list[Transfer]:
        query = (
            select(Transfer)
            .where(
                Transfer.status == OperationStatus.COMPLETED,
                Transfer.risk_status == RiskStatus.NORMAL,
            )
            .order_by(Transfer.created_at.desc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(query))

    def completed_operations(
        self,
        model,
        status,
        limit: int = 500,
    ) -> list:
        query = (
            select(model)
            .where(model.status == status)
            .order_by(model.created_at.desc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list(self.session.scalars(query))

    def has_operation_event(self, operation_type: str, operation_id: int) -> bool:
        return self.session.scalar(
            select(SuspiciousTransaction.id)
            .where(
                SuspiciousTransaction.operation_type == operation_type,
                SuspiciousTransaction.operation_id == operation_id,
            )
            .limit(1)
        ) is not None
