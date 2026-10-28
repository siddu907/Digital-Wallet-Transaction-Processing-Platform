from decimal import Decimal
from app.core.exceptions import DomainError
from sqlalchemy.exc import IntegrityError
from app.models import LedgerEntry
from app.models import LedgerType
from app.models import Refund
from app.models import RefundStatus
from app.models import OperationStatus
from sqlalchemy.orm import Session
from app.models import User
from app.models import WalletStatus
from app.models import Transfer
from app.models import utcnow
from app.models import RiskStatus
from app.services.financial_common import _positive_amount
from app.services.idempotency_service import _replay
from app.services.idempotency_service import _fingerprint
from app.services.financial_common import _check_count
from app.services.financial_common import _wallet
from app.services.financial_common import _ledger
from app.services.notification_service import _notify
from app.services.audit_service import _audit
from app.services.financial_common import _commit_idempotent
from app.services.transaction_limit_service import get_limits
from app.services.financial_common import ZERO
from app.services.financial_common import _lock_user_transactions
from app.services.financial_common import _maximum_transaction_amount_message
from app.services.audit_service import _audit_failure
from app.repositories.ledger_repository import LedgerRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.user_repository import UserRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.wallet_repository import WalletRepository
from app.repositories.suspicious_transaction_repository import SuspiciousTransactionRepository
from app.services.audit_service import _audit_system_event


def create_refund(db: Session, user: User, ledger_id: int, amount: Decimal, reason: str, key: str) -> Refund:
    try:
        _positive_amount(amount)
        digest = _fingerprint({"ledger_entry_id": ledger_id, "amount": amount, "reason": reason})
        _lock_user_transactions(db, user.id)
        replay = _replay(db, user.id, key, digest, "REFUND")
        if replay:
            return replay
        original = LedgerRepository(db).get(ledger_id, lock=True)
        if (
            original is None
            or original.transaction_type != LedgerType.TRANSFER_DEBIT
            or original.reference_entity != "TRANSFER"
        ):
            raise DomainError(
                "INVALID_REFUND",
                "Refunds can only be requested by the sender for a completed outgoing transfer.",
                400,
            )
        transfer = TransactionRepository(db).get_operation(
            Transfer,
            original.reference_id,
            lock=True,
        )
        if (
            transfer is None
            or transfer.status != OperationStatus.COMPLETED
            or transfer.reversed_at is not None
        ):
            raise DomainError(
                "INVALID_REFUND",
                "Refunds require a completed transfer that has not already been reversed.",
                409,
            )
        wallet = _wallet(db, original.wallet_id, lock=True)
        if wallet.owner_id != user.id or transfer.user_id != user.id:
            raise DomainError("FORBIDDEN", "Only the transfer sender may request its refund.", 403)
        if wallet.status == WalletStatus.CLOSED:
            raise DomainError("INVALID_REFUND", "Refunds cannot be returned to a closed wallet.", 409)
        refunded = RefundRepository(db).total_for_ledger(
            ledger_id,
            [
                RefundStatus.REQUESTED,
                RefundStatus.UNDER_REVIEW,
                RefundStatus.APPROVED,
                RefundStatus.COMPLETED,
            ],
        ) or ZERO
        if amount + Decimal(refunded) > original.amount:
            raise DomainError("INVALID_REFUND", "Refund amount exceeds the original transaction.", 409)
        limits = get_limits(db)
        if amount > limits.max_transaction_amount:
            raise DomainError(
                "TRANSACTION_LIMIT_EXCEEDED",
                _maximum_transaction_amount_message(
                    limits.max_transaction_amount,
                    wallet.currency,
                ),
                409,
            )
        _check_count(db, user.id, limits.max_transactions_per_day)
        row = Refund(ledger_entry_id=ledger_id, wallet_id=wallet.id, user_id=user.id, amount=amount, reason=reason)
        db.add(row)
        db.flush()
        _audit(
            db,
            user,
            "REFUND_CREATED",
            "REFUND",
            row.id,
            {
                "ledger_entry_id": ledger_id,
                "amount": str(amount),
                "currency": wallet.currency,
                "reason": reason,
            },
        )
        return _commit_idempotent(db, user, key, digest, "REFUND", row.id)
    except DomainError as exc:
        db.rollback()
        _audit_failure(db, user, "TRANSACTION_BLOCKED", "REFUND", ledger_id, exc.code, {"amount": str(amount)})
        raise
    except IntegrityError:
        db.rollback()
        replay = _replay(db, user.id, key, digest, "REFUND")
        if replay:
            return replay
        raise
    except Exception:
        db.rollback()
        raise


def mark_refund_under_review(db: Session, refund_id: int, reviewer: User) -> Refund:
    try:
        row = RefundRepository(db).get(refund_id, lock=True)
        if row is None:
            raise DomainError("REFUND_NOT_FOUND", "Refund was not found.", 404)
        if row.status != RefundStatus.REQUESTED:
            raise DomainError("INVALID_REFUND", "Only requested refunds can enter review.", 409)
        row.status = RefundStatus.UNDER_REVIEW
        row.reviewed_by = reviewer.id
        row.reviewed_at = utcnow()
        _audit(
            db,
            reviewer,
            "REFUND_UNDER_REVIEW",
            "REFUND",
            row.id,
            {"amount": str(row.amount), "wallet_id": row.wallet_id},
        )
        db.commit()
        return row
    except DomainError as exc:
        db.rollback()
        _audit_failure(db, reviewer, "TRANSACTION_BLOCKED", "REFUND", refund_id, exc.code)
        raise
    except Exception:
        db.rollback()
        raise


def _complete_approved_refund(
    db: Session,
    refund_id: int,
    reviewer: User | None = None,
) -> Refund:
    row = RefundRepository(db).get(refund_id, lock=True)
    if row is None:
        raise DomainError("REFUND_NOT_FOUND", "Refund was not found.", 404)
    if row.status == RefundStatus.COMPLETED:
        return row
    if row.status != RefundStatus.APPROVED:
        raise DomainError("INVALID_REFUND", "Only approved refunds can be completed.", 409)

    original = LedgerRepository(db).get(row.ledger_entry_id, lock=True)
    if (
        original is None
        or original.transaction_type != LedgerType.TRANSFER_DEBIT
        or original.reference_entity != "TRANSFER"
    ):
        raise DomainError("INVALID_REFUND", "The original outgoing transfer ledger entry is unavailable.", 409)
    transfer = TransactionRepository(db).get_operation(
        Transfer,
        original.reference_id,
        lock=True,
    )
    if (
        transfer is None
        or transfer.status != OperationStatus.COMPLETED
        or transfer.reversed_at is not None
    ):
        raise DomainError("INVALID_REFUND", "The original transfer is no longer eligible for refund.", 409)

    wallets = WalletRepository(db).get_many(
        [transfer.sender_wallet_id, transfer.receiver_wallet_id],
        lock=True,
    )
    wallet_by_id = {wallet.id: wallet for wallet in wallets}
    sender_wallet = wallet_by_id.get(transfer.sender_wallet_id)
    receiver_wallet = wallet_by_id.get(transfer.receiver_wallet_id)
    if sender_wallet is None or receiver_wallet is None:
        raise DomainError("WALLET_NOT_FOUND", "A transfer wallet was not found.", 404)
    if (
        sender_wallet.id != row.wallet_id
        or sender_wallet.owner_id != row.user_id
        or transfer.user_id != row.user_id
    ):
        raise DomainError("INVALID_REFUND", "The refund does not match the transfer sender.", 409)
    if sender_wallet.status == WalletStatus.CLOSED:
        raise DomainError("INVALID_REFUND", "Refunds cannot be returned to a closed wallet.", 409)
    if receiver_wallet.status == WalletStatus.CLOSED:
        raise DomainError("INVALID_REFUND", "Funds cannot be recovered from a closed wallet.", 409)
    if receiver_wallet.available_balance < row.amount:
        raise DomainError(
            "INSUFFICIENT_BALANCE",
            "The recipient does not have enough available balance to return this refund amount.",
            409,
        )

    ledger_repository = LedgerRepository(db)
    if ledger_repository.by_reference("REFUND", row.id) is None:
        receiver_before = receiver_wallet.available_balance
        sender_before = sender_wallet.available_balance
        receiver_wallet.available_balance -= row.amount
        sender_wallet.available_balance += row.amount
        _ledger(
            db,
            receiver_wallet,
            LedgerType.REFUND,
            row.amount,
            receiver_before,
            "REFUND",
            row.id,
            reviewer,
            "Approved refund returned to transfer sender",
        )
        _ledger(
            db,
            sender_wallet,
            LedgerType.REFUND,
            row.amount,
            sender_before,
            "REFUND",
            row.id,
            reviewer,
            "Approved refund received by transfer sender",
        )
    row.status = RefundStatus.COMPLETED
    row.completed_at = utcnow()
    suspicious = SuspiciousTransactionRepository(db).for_operation(
        "TRANSFER",
        transfer.id,
        lock=True,
    )
    if suspicious is not None and suspicious.status == RiskStatus.REVIEW_REQUIRED:
        suspicious.status = RiskStatus.NORMAL
        suspicious.reviewed_by = reviewer.id if reviewer is not None else row.reviewed_by
        suspicious.reviewed_at = utcnow()
        transfer.risk_status = RiskStatus.NORMAL
        _notify(
            db,
            row.user_id,
            "SUSPICIOUS_TRANSACTION_CLEARED",
            f"The risk review for transfer {transfer.reference} was resolved when the refund completed.",
        )
        _notify(
            db,
            receiver_wallet.owner_id,
            "SUSPICIOUS_TRANSACTION_CLEARED",
            f"The risk review for transfer {transfer.reference} was resolved when the refund completed.",
        )
        resolution_metadata = {
            "transfer_id": transfer.id,
            "refund_id": row.id,
            "status": RiskStatus.NORMAL.value,
        }
        if reviewer is not None:
            _audit(
                db,
                reviewer,
                "SUSPICIOUS_TRANSACTION_RESOLVED_BY_REFUND",
                "SUSPICIOUS_TRANSACTION",
                suspicious.id,
                resolution_metadata,
            )
        else:
            _audit_system_event(
                db,
                "SUSPICIOUS_TRANSACTION_RESOLVED_BY_REFUND",
                "SUSPICIOUS_TRANSACTION",
                suspicious.id,
                resolution_metadata,
            )
    _notify(
        db,
        row.user_id,
        "REFUND_APPROVED",
        f"Refund of {row.amount} {sender_wallet.currency} from the recipient was completed.",
    )
    _notify(
        db,
        receiver_wallet.owner_id,
        "REFUND_DEBITED",
        f"An approved refund of {row.amount} {receiver_wallet.currency} was returned to the transfer sender.",
    )
    if reviewer is not None:
        _audit(
            db,
            reviewer,
            "REFUND_COMPLETED",
            "REFUND",
            row.id,
            {
                "amount": str(row.amount),
                "currency": sender_wallet.currency,
                "sender_wallet_id": sender_wallet.id,
                "recipient_wallet_id": receiver_wallet.id,
            },
        )
    else:
        _audit_system_event(
            db,
            "REFUND_COMPLETED",
            "REFUND",
            row.id,
            {
                "amount": str(row.amount),
                "currency": sender_wallet.currency,
                "sender_wallet_id": sender_wallet.id,
                "recipient_wallet_id": receiver_wallet.id,
            },
        )
    db.commit()
    return row


def complete_approved_refunds(db: Session, limit: int = 100) -> int:
    refund_ids = [
        row.id for row in RefundRepository(db).approved_for_processing(limit)
    ]
    db.commit()
    completed = 0
    for refund_id in refund_ids:
        try:
            refund = RefundRepository(db).get(refund_id)
            reviewer = (
                UserRepository(db).by_id(refund.reviewed_by)
                if refund is not None and refund.reviewed_by
                else None
            )
            _complete_approved_refund(db, refund_id, reviewer)
            completed += 1
        except DomainError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
    return completed


def decide_refund(db: Session, refund_id: int, reviewer: User, approve: bool) -> Refund:
    try:
        row = RefundRepository(db).get(refund_id, lock=True)
        if row is None:
            raise DomainError("REFUND_NOT_FOUND", "Refund was not found.", 404)
        if approve and row.status == RefundStatus.APPROVED:
            db.commit()
            return _complete_approved_refund(db, refund_id, reviewer)
        if row.status not in {RefundStatus.REQUESTED, RefundStatus.UNDER_REVIEW}:
            raise DomainError("INVALID_REFUND", "Refund has already been reviewed.", 409)
        row.reviewed_by = reviewer.id
        row.reviewed_at = utcnow()
        if not approve:
            row.status = RefundStatus.REJECTED
            _notify(
                db,
                row.user_id,
                "REFUND_REJECTED",
                f"Refund request {row.id} was rejected.",
            )
            _audit(
                db,
                reviewer,
                "REFUND_REJECTED",
                "REFUND",
                row.id,
                {"amount": str(row.amount), "wallet_id": row.wallet_id},
            )
            db.commit()
            return row
        else:
            row.status = RefundStatus.APPROVED
            _audit(
                db,
                reviewer,
                "REFUND_APPROVED",
                "REFUND",
                row.id,
                {
                    "amount": str(row.amount),
                    "wallet_id": row.wallet_id,
                },
            )
            db.commit()
            return _complete_approved_refund(db, refund_id, reviewer)
    except DomainError as exc:
        db.rollback()
        _audit_failure(db, reviewer, "TRANSACTION_BLOCKED", "REFUND", refund_id, exc.code)
        raise
    except Exception:
        db.rollback()
        raise
