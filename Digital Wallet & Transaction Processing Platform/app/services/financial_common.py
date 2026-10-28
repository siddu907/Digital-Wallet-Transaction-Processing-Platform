from decimal import Decimal
from app.models import Deposit
from app.core.exceptions import DomainError
from app.repositories import FinanceRepository
from app.models import LedgerType
from app.models import Refund
from sqlalchemy.orm import Session
from app.models import Transfer
from app.models import User
from app.models import Wallet
from app.models import WalletStatus
from app.models import Withdrawal
from datetime import datetime
from datetime import time
from datetime import timezone
from app.models import utcnow
from app.services.idempotency_service import _record_idempotency

ZERO = Decimal("0.00")


def _maximum_transaction_amount_message(limit: Decimal, currency: str) -> str:
    return f"Maximum transaction amount is {currency} {limit:.2f}."


def _lock_user_transactions(db: Session, user_id: int) -> None:
    user = FinanceRepository(db).lock_user(user_id)
    if user is None:
        raise DomainError("USER_NOT_FOUND", "User was not found.", 404)


def _positive_amount(amount: Decimal) -> None:
    if amount <= ZERO:
        raise DomainError("INVALID_AMOUNT", "Amount must be greater than zero.", 400)


def _wallet(db: Session, wallet_id: int, *, lock: bool = False) -> Wallet:
    wallet = FinanceRepository(db).get_wallet(wallet_id, lock=lock)
    if wallet is None:
        raise DomainError("WALLET_NOT_FOUND", "Wallet was not found.", 404)
    return wallet


def _active(wallet: Wallet) -> None:
    if wallet.status == WalletStatus.FROZEN:
        raise DomainError("WALLET_FROZEN", "Wallet is frozen.", 409)
    if wallet.status == WalletStatus.CLOSED:
        raise DomainError("WALLET_CLOSED", "Wallet is closed.", 409)
    if wallet.status != WalletStatus.ACTIVE:
        raise DomainError("WALLET_UNAVAILABLE", "Wallet is not active.", 409)


def _daily_start() -> datetime:
    now = utcnow()
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


def _check_count(db: Session, user_id: int, max_count: int) -> None:
    start = _daily_start()
    count = FinanceRepository(db).count_user_operations(
        user_id,
        start,
        (Deposit, Transfer, Withdrawal, Refund),
    )
    if count >= max_count:
        raise DomainError("TRANSACTION_LIMIT_EXCEEDED", "Daily transaction count limit exceeded.", 409)


def _check_daily_amount(db: Session, user_id: int, amount: Decimal, limit: Decimal, model, label: str) -> None:
    start = _daily_start()
    used = FinanceRepository(db).sum_user_operation_amount(user_id, start, model)
    if Decimal(used) + amount > limit:
        raise DomainError("TRANSACTION_LIMIT_EXCEEDED", f"Daily {label} limit exceeded.", 409)


def _ledger(db: Session, wallet: Wallet, kind: LedgerType, amount: Decimal, before: Decimal, reference_entity: str, reference_id: int, user: User | None, description: str) -> None:
    FinanceRepository(db).append_ledger(wallet, kind, amount, before, reference_entity, reference_id, user, description)


def _commit_idempotent(db: Session, user: User, key: str, digest: str, entity: str, entity_id: int):
    _record_idempotency(db, user.id, key, digest, entity, entity_id)
    db.commit()
    model = {"DEPOSIT": Deposit, "TRANSFER": Transfer, "WITHDRAWAL": Withdrawal, "REFUND": Refund}[entity]
    return FinanceRepository(db).get_entity(model, entity_id)
