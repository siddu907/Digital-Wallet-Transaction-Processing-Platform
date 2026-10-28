from decimal import Decimal
from app.core.exceptions import DomainError
from sqlalchemy.exc import IntegrityError
from app.models import LedgerType
from app.models import OperationStatus
from sqlalchemy.orm import Session
from app.models import User
from app.models import Withdrawal
from app.models import utcnow
from app.services.financial_common import _positive_amount
from app.services.idempotency_service import _replay
from app.services.idempotency_service import _fingerprint
from app.services.transaction_limit_service import get_limits
from app.services.financial_common import _check_count
from app.services.financial_common import _check_daily_amount
from app.services.financial_common import _wallet
from app.services.financial_common import _active
from app.services.financial_common import _ledger
from app.services.notification_service import _notify
from app.services.audit_service import _audit
from app.services.financial_common import _commit_idempotent
from app.services.financial_common import _lock_user_transactions
from app.services.financial_common import _maximum_transaction_amount_message
from app.services.audit_service import _audit_failure, _flag_limit_attempt


def create_withdrawal(db: Session, user: User, wallet_id: int, amount: Decimal, key: str) -> Withdrawal:
    try:
        _positive_amount(amount)
        digest = _fingerprint({"wallet_id": wallet_id, "amount": amount})
        _lock_user_transactions(db, user.id)
        replay = _replay(db, user.id, key, digest, "WITHDRAWAL")
        if replay:
            return replay
        wallet = _wallet(db, wallet_id, lock=True)
        if wallet.owner_id != user.id:
            raise DomainError("FORBIDDEN", "You do not have access to this wallet.", 403)
        _active(wallet)
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
        _check_daily_amount(db, user.id, amount, limits.daily_withdrawal_limit, Withdrawal, "withdrawal")
        _check_count(db, user.id, limits.max_transactions_per_day)
        if wallet.available_balance < amount:
            raise DomainError("INSUFFICIENT_BALANCE", "Insufficient wallet balance.", 409)
        before = wallet.available_balance
        row = Withdrawal(wallet_id=wallet.id, user_id=user.id, amount=amount, currency=wallet.currency, status=OperationStatus.COMPLETED, completed_at=utcnow())
        db.add(row)
        db.flush()
        wallet.available_balance -= amount
        _ledger(db, wallet, LedgerType.WITHDRAWAL, amount, before, "WITHDRAWAL", row.id, user, "Wallet withdrawal")
        _notify(db, user.id, "WITHDRAWAL_COMPLETED", f"Withdrawal of {amount} {wallet.currency} completed.")
        metadata = {"wallet_id": wallet.id, "amount": str(amount), "currency": wallet.currency}
        _audit(db, user, "WITHDRAWAL_CREATED", "WITHDRAWAL", row.id, metadata)
        _audit(db, user, "WITHDRAWAL_COMPLETED", "WITHDRAWAL", row.id, metadata)
        return _commit_idempotent(db, user, key, digest, "WITHDRAWAL", row.id)
    except DomainError as exc:
        db.rollback()
        if exc.code == "TRANSACTION_LIMIT_EXCEEDED":
            _flag_limit_attempt(db, user, "WITHDRAWAL", wallet_id, amount, exc.code)
        else:
            _notify(db, user.id, "WITHDRAWAL_FAILED", f"Withdrawal attempt for {amount} failed: {exc.message}")
            _audit_failure(db, user, "TRANSACTION_BLOCKED", "WITHDRAWAL", wallet_id, exc.code, {"amount": str(amount)})
        raise
    except IntegrityError:
        db.rollback()
        replay = _replay(db, user.id, key, digest, "WITHDRAWAL")
        if replay:
            return replay
        raise
    except Exception:
        db.rollback()
        raise
