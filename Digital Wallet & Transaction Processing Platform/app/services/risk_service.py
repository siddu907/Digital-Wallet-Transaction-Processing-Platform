from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import (
    Deposit,
    Refund,
    Notification,
    OperationStatus,
    RefundStatus,
    RiskStatus,
    SuspiciousTransaction,
    TransactionLimit,
    Transfer,
    User,
    Wallet,
    Withdrawal,
    utcnow,
)
from app.repositories.suspicious_transaction_repository import SuspiciousTransactionRepository
from app.repositories.ledger_repository import LedgerRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.transaction_limit_repository import TransactionLimitRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.audit_service import _audit
from app.services.audit_service import _audit_system_event
from app.services.notification_service import _notify


def _recent_activity_counts(
    db: Session,
    user_id: int,
    start: datetime,
    end: datetime | None = None,
) -> tuple[int, int]:
    return SuspiciousTransactionRepository(db).activity_counts(user_id, start, end)


def assess_transfer(
    db: Session,
    sender: Wallet,
    receiver: Wallet,
    amount: Decimal,
    limits: TransactionLimit,
) -> tuple[RiskStatus, str | None]:
    if amount > limits.suspicious_amount_threshold:
        return RiskStatus.REVIEW_REQUIRED, "Amount exceeds configured suspicious-transaction threshold"
    recently_frozen = utcnow() - timedelta(days=1)
    if any(wallet.last_frozen_at and wallet.last_frozen_at >= recently_frozen for wallet in (sender, receiver)):
        return RiskStatus.REVIEW_REQUIRED, "Wallet was recently frozen"
    now = utcnow()
    recent_transfers, recent_operations = _recent_activity_counts(
        db,
        sender.owner_id,
        now - timedelta(minutes=10),
        now,
    )
    if recent_transfers >= 2:
        return RiskStatus.REVIEW_REQUIRED, "At least three transfers occurred within ten minutes"
    if recent_operations >= 4:
        return RiskStatus.REVIEW_REQUIRED, "Unusual transaction frequency: at least five financial operations within ten minutes"
    return RiskStatus.NORMAL, None


def scan_suspicious_transactions(db: Session) -> int:
    limits = TransactionLimitRepository(db).get_current()
    threshold = limits.suspicious_amount_threshold if limits else Decimal("50000")
    risk_repository = SuspiciousTransactionRepository(db)
    wallet_repository = WalletRepository(db)
    transfers = risk_repository.completed_transfers(limit=500)
    created = 0
    for transfer in transfers:
        wallets = {
            wallet.id: wallet
            for wallet in wallet_repository.get_many(
                [transfer.sender_wallet_id, transfer.receiver_wallet_id]
            )
        }
        sender = wallets.get(transfer.sender_wallet_id)
        receiver = wallets.get(transfer.receiver_wallet_id)
        if sender is None or receiver is None:
            continue
        reason = None
        if transfer.amount > threshold:
            reason = "Amount exceeds configured suspicious-transaction threshold"
        elif any(
            wallet.last_frozen_at and wallet.last_frozen_at >= utcnow() - timedelta(days=1)
            for wallet in (sender, receiver)
        ):
            reason = "Wallet was recently frozen"
        else:
            recent_count, recent_operations = _recent_activity_counts(
                db,
                transfer.user_id,
                transfer.created_at - timedelta(minutes=10),
                transfer.created_at,
            )
            if recent_count >= 3:
                reason = "At least three transfers occurred within ten minutes"
            elif recent_operations >= 5:
                reason = "Unusual transaction frequency: at least five financial operations within ten minutes"
        if reason is None:
            continue
        transfer.risk_status = RiskStatus.REVIEW_REQUIRED
        db.add(
            SuspiciousTransaction(
                transfer_id=transfer.id,
                user_id=transfer.user_id,
                wallet_id=sender.id,
                operation_type="TRANSFER",
                operation_id=transfer.id,
                amount=transfer.amount,
                status=RiskStatus.REVIEW_REQUIRED,
                reason=reason,
            )
        )
        _notify(
            db,
            transfer.user_id,
            "SUSPICIOUS_TRANSACTION",
            f"Transfer {transfer.reference} was flagged for review: {reason}.",
        )
        _notify(
            db,
            receiver.owner_id,
            "SUSPICIOUS_TRANSACTION",
            f"Incoming transfer {transfer.reference} was flagged for review.",
        )
        _audit_system_event(
            db,
            "SUSPICIOUS_TRANSACTION_DETECTED",
            "TRANSFER",
            transfer.id,
            {"reason": reason, "amount": str(transfer.amount)},
        )
        created += 1

    financial_ops = (
        (Deposit, "DEPOSIT", OperationStatus.COMPLETED),
        (Withdrawal, "WITHDRAWAL", OperationStatus.COMPLETED),
        (Refund, "REFUND", RefundStatus.COMPLETED),
    )
    for model, operation, completed_status in financial_ops:
        rows = risk_repository.completed_operations(
            model,
            completed_status,
            limit=500,
        )
        for operation_row in rows:
            wallet = wallet_repository.get(operation_row.wallet_id)
            if wallet is None:
                continue
            amount_exceeds_threshold = operation_row.amount > threshold
            wallet_recently_frozen = bool(
                wallet.last_frozen_at
                and wallet.last_frozen_at >= utcnow() - timedelta(days=1)
            )
            _, recent_operations = _recent_activity_counts(
                db,
                operation_row.user_id,
                operation_row.created_at - timedelta(minutes=10),
                operation_row.created_at,
            )
            unusual_frequency = recent_operations >= 5
            if not amount_exceeds_threshold and not wallet_recently_frozen and not unusual_frequency:
                continue
            if risk_repository.has_operation_event(operation, operation_row.id):
                continue
            reason = (
                "Amount exceeds configured suspicious-transaction threshold"
                if amount_exceeds_threshold
                else "Wallet was recently frozen"
                if wallet_recently_frozen
                else "Unusual transaction frequency: at least five financial operations within ten minutes"
            )
            db.add(
                SuspiciousTransaction(
                    user_id=operation_row.user_id,
                    wallet_id=wallet.id,
                    operation_type=operation,
                    operation_id=operation_row.id,
                    amount=operation_row.amount,
                    status=RiskStatus.REVIEW_REQUIRED,
                    reason=reason,
                )
            )
            _notify(
                db,
                operation_row.user_id,
                "SUSPICIOUS_TRANSACTION",
                f"{operation} {operation_row.reference} was flagged for review.",
            )
            _audit_system_event(
                db,
                "SUSPICIOUS_TRANSACTION_DETECTED",
                operation,
                operation_row.id,
                {"reason": reason, "amount": str(operation_row.amount)},
            )
            created += 1
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return created


def review_suspicious_transaction(
    db: Session,
    suspicious_id: int,
    reviewer: User,
    status: RiskStatus,
) -> SuspiciousTransaction:
    if status == RiskStatus.REVIEW_REQUIRED:
        raise DomainError("INVALID_REVIEW_STATUS", "Review must resolve to NORMAL or BLOCKED.", 422)
    suspicious_repository = SuspiciousTransactionRepository(db)
    row = suspicious_repository.get(suspicious_id)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Suspicious transaction was not found.", 404)
    transfer_id = row.transfer_id or (
        row.operation_id if row.operation_type == "TRANSFER" else None
    )
    transfer = (
        TransactionRepository(db).get_operation(Transfer, transfer_id, lock=True)
        if transfer_id
        else None
    )
    row = suspicious_repository.get(suspicious_id, refresh=True)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Suspicious transaction was not found.", 404)
    if row.status != RiskStatus.REVIEW_REQUIRED:
        raise DomainError("INVALID_REVIEW_STATUS", "This transaction has already been reviewed.", 409)
    if transfer is not None:
        if (
            status == RiskStatus.BLOCKED
            and transfer.status == OperationStatus.COMPLETED
            and transfer.reversed_at is None
        ):
            original_debit = LedgerRepository(db).transfer_debit(transfer.id)
            if original_debit is not None:
                refund_amount = RefundRepository(db).total_for_ledger(
                    original_debit.id,
                    [
                        RefundStatus.REQUESTED,
                        RefundStatus.UNDER_REVIEW,
                        RefundStatus.APPROVED,
                        RefundStatus.COMPLETED,
                    ],
                ) or Decimal("0")
                if refund_amount > 0:
                    raise DomainError(
                        "REFUND_IN_PROGRESS",
                        "A related refund has been requested or completed; this transfer cannot be blocked.",
                        409,
                    )
            wallets = WalletRepository(db).get_many(
                [transfer.sender_wallet_id, transfer.receiver_wallet_id],
                lock=True,
            )
            by_id = {wallet.id: wallet for wallet in wallets}
            sender = by_id.get(transfer.sender_wallet_id)
            receiver = by_id.get(transfer.receiver_wallet_id)
            if sender is None or receiver is None:
                raise DomainError("WALLET_NOT_FOUND", "A transfer wallet was not found.", 404)
            if receiver.available_balance < transfer.amount:
                raise DomainError(
                    "INSUFFICIENT_BALANCE",
                    "The transfer cannot be blocked because the receiver has already spent the funds.",
                    409,
                )
            from app.models import LedgerType
            from app.services.financial_common import _ledger

            sender_before = sender.available_balance
            receiver_before = receiver.available_balance
            sender.available_balance += transfer.amount
            receiver.available_balance -= transfer.amount
            _ledger(
                db,
                sender,
                LedgerType.REVERSAL,
                transfer.amount,
                sender_before,
                "TRANSFER",
                transfer.id,
                reviewer,
                "Suspicious transfer blocked and reversed",
            )
            _ledger(
                db,
                receiver,
                LedgerType.REVERSAL,
                transfer.amount,
                receiver_before,
                "TRANSFER",
                transfer.id,
                reviewer,
                "Suspicious transfer blocked and reversed",
            )
            transfer.reversed_at = utcnow()
            _notify(
                db,
                sender.owner_id,
                "TRANSFER_REVERSED",
                f"Completed transfer {transfer.reference} was reversed after risk review.",
            )
            _notify(
                db,
                receiver.owner_id,
                "TRANSFER_REVERSED",
                f"Completed transfer {transfer.reference} was reversed after risk review.",
            )
    row = suspicious_repository.get(suspicious_id, lock=True, refresh=True)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Suspicious transaction was not found.", 404)
    if row.status != RiskStatus.REVIEW_REQUIRED:
        raise DomainError("INVALID_REVIEW_STATUS", "This transaction has already been reviewed.", 409)
    row.status = status
    row.reviewed_by = reviewer.id
    row.reviewed_at = utcnow()
    if transfer is not None:
        transfer.risk_status = status
    if row.user_id:
        resolution_event = (
            "SUSPICIOUS_TRANSACTION_BLOCKED"
            if status == RiskStatus.BLOCKED
            else "SUSPICIOUS_TRANSACTION_CLEARED"
        )
        _notify(
            db,
            row.user_id,
            resolution_event,
            f"Your flagged {row.operation_type or 'transaction'} was reviewed as {status.value}.",
        )
    _audit(
        db,
        reviewer,
        "SUSPICIOUS_TRANSACTION_REVIEWED",
        "SUSPICIOUS_TRANSACTION",
        row.id,
        {
            "status": status.value,
            "transfer_id": row.transfer_id,
            "operation_type": row.operation_type,
            "operation_id": row.operation_id,
            "amount": str(row.amount) if row.amount is not None else None,
        },
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return row


def list_suspicious_transactions(
    db: Session,
    page: int,
    page_size: int,
) -> list[SuspiciousTransaction]:
    return SuspiciousTransactionRepository(db).list(page=page, page_size=page_size)


def get_suspicious_transaction(db: Session, suspicious_id: int) -> SuspiciousTransaction:
    row = SuspiciousTransactionRepository(db).get(suspicious_id)
    if row is None:
        from app.core.exceptions import DomainError

        raise DomainError("TRANSACTION_NOT_FOUND", "Suspicious transaction was not found.", 404)
    return row
