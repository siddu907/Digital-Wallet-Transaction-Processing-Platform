from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Deposit,
    LedgerEntry,
    OperationStatus,
    Refund,
    Transfer,
    Withdrawal,
)


class ReportRepository:
    def __init__(self, session: Session):
        self.session = session

    def ledger_totals(self, start: datetime, end: datetime) -> tuple[int, Decimal]:
        statement = select(
            func.count(LedgerEntry.id),
            func.coalesce(func.sum(LedgerEntry.amount), 0),
        ).where(LedgerEntry.created_at >= start, LedgerEntry.created_at < end)
        count, volume = self.session.execute(statement).one()
        return int(count), Decimal(volume)

    def daily_operation_totals(
        self,
        start: datetime,
        end: datetime,
    ) -> tuple[int, Decimal]:
        operation_models = (Deposit, Transfer, Withdrawal, Refund)
        count = 0
        volume = Decimal("0")
        for model in operation_models:
            count += self.session.scalar(
                select(func.count()).select_from(model).where(
                    model.created_at >= start,
                    model.created_at < end,
                )
            ) or 0
            volume += self.session.scalar(
                select(func.coalesce(func.sum(model.amount), 0)).where(
                    model.created_at >= start,
                    model.created_at < end,
                    model.status == OperationStatus.COMPLETED,
                )
            ) or Decimal("0")
        return count, volume
