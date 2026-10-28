from datetime import datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import OperationStatus, RefundStatus, RiskStatus, WalletStatus
from app.models import (
    Deposit,
    LedgerEntry,
    Notification,
    Refund,
    SuspiciousTransaction,
    Transfer,
    User,
    Wallet,
    Withdrawal,
    utcnow,
)


class DashboardRepository:
    def __init__(self, session: Session):
        self.session = session

    def admin(self) -> dict:
        return admin_dashboard(self.session)

    def support(self) -> dict:
        return support_dashboard(self.session)

    def customer(self, user: User) -> dict:
        return customer_dashboard(self.session, user)


def admin_dashboard(db: Session) -> dict:
    today = datetime.combine(utcnow().date(), time.min, tzinfo=timezone.utc)
    operations = (Deposit, Transfer, Withdrawal, Refund)
    balances_by_currency = db.execute(
        select(
            Wallet.currency,
            func.coalesce(
                func.sum(Wallet.available_balance + Wallet.pending_balance),
                0,
            ),
        ).group_by(Wallet.currency)
    ).all()
    return {
        "total_users": db.scalar(select(func.count()).select_from(User)) or 0,
        "active_wallets": db.scalar(
            select(func.count()).select_from(Wallet).where(Wallet.status == WalletStatus.ACTIVE)
        ) or 0,
        "total_wallet_balance": db.scalar(
            select(
                func.coalesce(
                    func.sum(Wallet.available_balance + Wallet.pending_balance),
                    0,
                )
            )
        ) or Decimal("0"),
        "wallet_balances_by_currency": {
            currency: balance for currency, balance in balances_by_currency
        },
        "today_transactions": sum(
            db.scalar(select(func.count()).select_from(model).where(model.created_at >= today)) or 0
            for model in operations
        ),
        "today_transaction_volume": sum(
            db.scalar(
                select(func.coalesce(func.sum(model.amount), 0)).where(
                    model.created_at >= today,
                    model.status == OperationStatus.COMPLETED,
                )
            ) or Decimal("0")
            for model in operations
        ),
        "failed_transactions": sum(
            db.scalar(
                select(func.count()).select_from(model).where(model.status == OperationStatus.FAILED)
            ) or 0
            for model in operations
        ),
        "suspicious_transactions": db.scalar(
            select(func.count())
            .select_from(SuspiciousTransaction)
            .where(
                SuspiciousTransaction.status.in_(
                    [RiskStatus.REVIEW_REQUIRED, RiskStatus.BLOCKED]
                )
            )
        ) or 0,
    }


def support_dashboard(db: Session) -> dict:
    operations = (Deposit, Transfer, Withdrawal, Refund)
    return {
        "pending_reviews": db.scalar(
            select(func.count())
            .select_from(SuspiciousTransaction)
            .where(SuspiciousTransaction.status == RiskStatus.REVIEW_REQUIRED)
        ) or 0,
        "suspicious_transactions": db.scalar(
            select(func.count())
            .select_from(SuspiciousTransaction)
            .where(
                SuspiciousTransaction.status.in_(
                    [RiskStatus.REVIEW_REQUIRED, RiskStatus.BLOCKED]
                )
            )
        ) or 0,
        "failed_transactions": sum(
            db.scalar(
                select(func.count()).select_from(model).where(model.status == OperationStatus.FAILED)
            ) or 0
            for model in operations
        ),
        "refund_requests": db.scalar(
            select(func.count())
            .select_from(Refund)
            .where(Refund.status.in_([RefundStatus.REQUESTED, RefundStatus.UNDER_REVIEW]))
        ) or 0,
        "frozen_wallets": db.scalar(
            select(func.count()).select_from(Wallet).where(Wallet.status == WalletStatus.FROZEN)
        ) or 0,
    }


def customer_dashboard(db: Session, user: User) -> dict:
    wallet_ids = select(Wallet.id).where(Wallet.owner_id == user.id)
    wallets = db.scalars(select(Wallet).where(Wallet.owner_id == user.id)).all()
    recent_ledger = (
        select(LedgerEntry)
        .where(LedgerEntry.wallet_id.in_(wallet_ids))
        .order_by(LedgerEntry.created_at.desc())
        .limit(10)
    )
    return {
        "wallets": wallets,
        "wallet_balance": {
            wallet.currency: {
                "available_balance": wallet.available_balance,
                "pending_balance": wallet.pending_balance,
            }
            for wallet in wallets
        },
        "recent_transactions": db.scalars(recent_ledger).all(),
        "total_deposits": db.scalar(
            select(func.coalesce(func.sum(Deposit.amount), 0)).where(
                Deposit.user_id == user.id,
                Deposit.status == OperationStatus.COMPLETED,
            )
        ) or Decimal("0"),
        "total_transfers": db.scalar(
            select(func.coalesce(func.sum(Transfer.amount), 0)).where(
                Transfer.user_id == user.id,
                Transfer.status == OperationStatus.COMPLETED,
            )
        ) or Decimal("0"),
        "total_withdrawals": db.scalar(
            select(func.coalesce(func.sum(Withdrawal.amount), 0)).where(
                Withdrawal.user_id == user.id,
                Withdrawal.status == OperationStatus.COMPLETED,
            )
        ) or Decimal("0"),
        "pending_transactions": sum(
            db.scalar(
                select(func.count()).select_from(model).where(
                    model.user_id == user.id,
                    model.status.in_([OperationStatus.PENDING, OperationStatus.PROCESSING]),
                )
            ) or 0
            for model in (Deposit, Transfer, Withdrawal)
        ) + (
            db.scalar(
                select(func.count()).select_from(Refund).where(
                    Refund.user_id == user.id,
                    Refund.status.in_([RefundStatus.REQUESTED, RefundStatus.UNDER_REVIEW]),
                )
            ) or 0
        ),
    }
