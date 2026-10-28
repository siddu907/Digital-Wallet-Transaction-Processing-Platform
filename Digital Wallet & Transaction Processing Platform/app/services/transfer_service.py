from decimal import Decimal
from app.core.exceptions import DomainError
from sqlalchemy.exc import IntegrityError
from app.models import LedgerType, RiskStatus
from app.models import OperationStatus
from sqlalchemy.orm import Session
from app.models import SuspiciousTransaction
from app.models import Transfer
from app.models import User
from app.models import Wallet
from app.models import utcnow
from app.services.financial_common import _positive_amount
from app.services.idempotency_service import _replay
from app.services.idempotency_service import _fingerprint
from app.services.transaction_limit_service import get_limits
from app.services.financial_common import _check_count
from app.services.financial_common import _check_daily_amount
from app.services.financial_common import _active
from app.services.financial_common import _ledger
from app.services.notification_service import _notify
from app.services.audit_service import _audit
from app.services.financial_common import _commit_idempotent
from app.services.risk_service import assess_transfer
from app.services.financial_common import _lock_user_transactions
from app.services.financial_common import _maximum_transaction_amount_message
from app.services.audit_service import _audit_failure, _flag_limit_attempt
from app.repositories.wallet_repository import WalletRepository


def create_transfer(db: Session, user: User, sender_id: int, receiver_id: int, amount: Decimal, key: str) -> Transfer:
    try:
        _positive_amount(amount)
        digest = _fingerprint({"sender_wallet_id": sender_id, "receiver_wallet_id": receiver_id, "amount": amount})
        _lock_user_transactions(db, user.id)
        replay = _replay(db, user.id, key, digest, "TRANSFER")
        if replay:
            return replay
        if sender_id == receiver_id:
            raise DomainError("INVALID_TRANSFER", "Sender and receiver wallets must be different.", 400)
        locked = WalletRepository(db).get_many_for_transfer(sender_id, receiver_id)
        wallets = {wallet.id: wallet for wallet in locked}
        sender = wallets.get(sender_id)
        receiver = wallets.get(receiver_id)
        if sender is None or receiver is None:
            raise DomainError("WALLET_NOT_FOUND", "Sender or receiver wallet was not found.", 404)
        if sender.owner_id != user.id:
            raise DomainError("FORBIDDEN", "You do not own the sender wallet.", 403)
        if sender.owner_id == receiver.owner_id:
            raise DomainError("INVALID_TRANSFER", "Users cannot transfer money to themselves.", 400)
        _active(sender)
        _active(receiver)
        if sender.currency != receiver.currency:
            raise DomainError("INVALID_TRANSFER", "Wallet currencies must match.", 400)
        limits = get_limits(db)
        if amount > limits.max_transaction_amount:
            raise DomainError(
                "TRANSACTION_LIMIT_EXCEEDED",
                _maximum_transaction_amount_message(
                    limits.max_transaction_amount,
                    sender.currency,
                ),
                409,
            )
        _check_daily_amount(db, user.id, amount, limits.daily_transfer_limit, Transfer, "transfer")
        _check_count(db, user.id, limits.max_transactions_per_day)
        if sender.available_balance < amount:
            raise DomainError("INSUFFICIENT_BALANCE", "Insufficient wallet balance.", 409)
        risk_status, risk_reason = assess_transfer(db, sender, receiver, amount, limits)
        row = Transfer(sender_wallet_id=sender.id, receiver_wallet_id=receiver.id, user_id=user.id, amount=amount, currency=sender.currency, status=OperationStatus.COMPLETED, completed_at=utcnow(), risk_status=risk_status)
        db.add(row)
        db.flush()
        sender_before = sender.available_balance
        receiver_before = receiver.available_balance
        sender.available_balance -= amount
        receiver.available_balance += amount
        _ledger(db, sender, LedgerType.TRANSFER_DEBIT, amount, sender_before, "TRANSFER", row.id, user, "Wallet transfer sent")
        _ledger(db, receiver, LedgerType.TRANSFER_CREDIT, amount, receiver_before, "TRANSFER", row.id, user, "Wallet transfer received")
        _notify(db, user.id, "TRANSFER_COMPLETED", f"Transfer of {amount} {sender.currency} completed.")
        _notify(db, receiver.owner_id, "TRANSFER_RECEIVED", f"Received {amount} {receiver.currency}.")
        audit_metadata = {
            "sender_wallet_id": sender.id,
            "receiver_wallet_id": receiver.id,
            "amount": str(amount),
            "currency": sender.currency,
        }
        _audit(db, user, "TRANSFER_CREATED", "TRANSFER", row.id, audit_metadata)
        _audit(db, user, "TRANSFER_COMPLETED", "TRANSFER", row.id, audit_metadata)
        if risk_reason:
            db.add(
                SuspiciousTransaction(
                    transfer_id=row.id,
                    user_id=user.id,
                    wallet_id=sender.id,
                    operation_type="TRANSFER",
                    operation_id=row.id,
                    amount=amount,
                    status=RiskStatus.REVIEW_REQUIRED,
                    reason=risk_reason,
                )
            )
            _notify(db, user.id, "SUSPICIOUS_TRANSACTION", "A transfer was flagged for review.")
            _notify(db, receiver.owner_id, "SUSPICIOUS_TRANSACTION", "A transfer was flagged for review.")
        return _commit_idempotent(db, user, key, digest, "TRANSFER", row.id)
    except DomainError as exc:
        db.rollback()
        if exc.code == "TRANSACTION_LIMIT_EXCEEDED":
            _flag_limit_attempt(db, user, "TRANSFER", sender_id, amount, exc.code)
        else:
            _notify(db, user.id, "TRANSFER_FAILED", f"Transfer attempt for {amount} failed: {exc.message}")
            _audit_failure(db, user, "TRANSACTION_BLOCKED", "TRANSFER", sender_id, exc.code, {"receiver_wallet_id": receiver_id, "amount": str(amount)})
        raise
    except IntegrityError:
        db.rollback()
        replay = _replay(db, user.id, key, digest, "TRANSFER")
        if replay:
            return replay
        raise
    except Exception:
        db.rollback()
        raise
