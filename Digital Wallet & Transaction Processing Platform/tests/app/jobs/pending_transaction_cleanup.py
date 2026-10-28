from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Deposit,
    Notification,
    OperationStatus,
    Refund,
    RefundStatus,
    Transfer,
    Withdrawal,
    utcnow,
)
from app.services.audit_service import _audit_system_event


def _failure_event(model) -> str:
    return f"{model.__name__.upper()}_FAILED"


def cleanup_pending_transactions(db: Session, age: timedelta = timedelta(hours=24)) -> int:
    cutoff = utcnow() - age
    changed = 0
    for model in (Deposit, Transfer, Withdrawal):
        rows = db.scalars(
            select(model)
            .where(
                model.status.in_([OperationStatus.PENDING, OperationStatus.PROCESSING]),
                model.created_at < cutoff,
            )
            .with_for_update()
        ).all()
        for row in rows:
            row.status = OperationStatus.FAILED
            event = _failure_event(model)
            _audit_system_event(
                db,
                event,
                model.__tablename__.upper(),
                row.id,
                {"reason": "pending transaction expired"},
            )
            recipient_user = getattr(row, "user_id", None)
            if recipient_user:
                db.add(
                    Notification(
                        user_id=recipient_user,
                        event=event,
                        message=f"Your pending {model.__name__.lower()} expired and failed.",
                    )
                )
            changed += 1
    stale_refunds = db.scalars(
        select(Refund)
        .where(
            Refund.status.in_([RefundStatus.REQUESTED, RefundStatus.UNDER_REVIEW]),
            Refund.created_at < cutoff,
        )
        .with_for_update()
    ).all()
    for refund in stale_refunds:
        refund.status = RefundStatus.FAILED
        _audit_system_event(
            db,
            "REFUND_FAILED",
            "REFUND",
            refund.id,
            {"reason": "refund request expired before review"},
        )
        db.add(
            Notification(
                user_id=refund.user_id,
                event="REFUND_FAILED",
                message=f"Refund request {refund.id} expired before review.",
            )
        )
        changed += 1
    db.commit()
    return changed


run = cleanup_pending_transactions
