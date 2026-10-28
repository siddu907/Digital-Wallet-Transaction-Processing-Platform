from decimal import Decimal

from app.core.exceptions import DomainError
from app.repositories import FinanceRepository
from app.repositories.transaction_limit_repository import TransactionLimitRepository
from sqlalchemy.orm import Session
from app.models import TransactionLimit
from app.config import settings
from app.models import User
from app.services.audit_service import _audit


def get_limits(db: Session, *, for_update: bool = False) -> TransactionLimit:
    row = (
        FinanceRepository(db).get_limits_for_update()
        if for_update
        else TransactionLimitRepository(db).get_current()
    )
    if row is None:
        row = TransactionLimit(
            id=1,
            max_transaction_amount=Decimal(settings.max_transaction_amount),
            daily_transfer_limit=Decimal(settings.daily_transfer_limit),
            daily_withdrawal_limit=Decimal(settings.daily_withdrawal_limit),
            max_transactions_per_day=settings.max_transactions_per_day,
            suspicious_amount_threshold=Decimal(settings.suspicious_amount_threshold),
        )
        db.add(row)
        db.flush()
    return row


def update_limits(db: Session, user: User, changes: dict) -> TransactionLimit:
    if not changes:
        raise DomainError("INVALID_LIMIT_UPDATE", "Provide at least one limit to update.", 422)
    row = get_limits(db, for_update=True)
    for field, value in changes.items():
        setattr(row, field, value)
    _audit(db, user, "TRANSACTION_LIMIT_CHANGED", "TRANSACTION_LIMITS", row.id, changes)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return row
