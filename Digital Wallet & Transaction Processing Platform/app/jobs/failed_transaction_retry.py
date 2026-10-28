from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import (
    Deposit,
    LedgerEntry,
    LedgerType,
    OperationStatus,
    Transfer,
    Wallet,
    WalletStatus,
    Withdrawal,
    utcnow,
)
from app.services.transaction_limit_service import get_limits
from app.services.audit_service import _audit_system_event
from app.services.notification_service import _notify


def _retry_is_allowed(
    row,
    wallets: list[Wallet],
    *,
    expected_wallet_count: int,
) -> tuple[bool, str | None]:
    if len(wallets) != expected_wallet_count or len({wallet.id for wallet in wallets}) != expected_wallet_count:
        return False, "wallet unavailable"
    if any(wallet.status != WalletStatus.ACTIVE for wallet in wallets):
        return False, "wallet is not active"
    if any(wallet.currency != row.currency for wallet in wallets):
        return False, "wallet currency changed"
    if isinstance(row, Transfer):
        if wallets[0].owner_id == wallets[1].owner_id:
            return False, "sender and receiver have the same owner"
    if row.amount <= 0:
        return False, "transaction amount is invalid"
    return True, None


def retry_failed_transactions(db: Session) -> int:
    retried = 0
    limits = get_limits(db)
    candidates = []
    candidates.extend(
        db.scalars(
            select(Deposit)
            .where(Deposit.status == OperationStatus.FAILED)
            .with_for_update()
        ).all()
    )
    candidates.extend(
        db.scalars(
            select(Withdrawal)
            .where(Withdrawal.status == OperationStatus.FAILED)
            .with_for_update()
        ).all()
    )
    candidates.extend(
        db.scalars(
            select(Transfer)
            .where(Transfer.status == OperationStatus.FAILED)
            .with_for_update()
        ).all()
    )
    try:
        for row in candidates:
            reference_entity = row.__tablename__.upper()[:-1]
            if db.scalar(
                select(LedgerEntry.id).where(
                    LedgerEntry.reference_entity == reference_entity,
                    LedgerEntry.reference_id == row.id,
                )
            ):
                continue
            if row.amount > limits.max_transaction_amount:
                _audit_system_event(
                    db,
                    "TRANSACTION_RETRY_DEFERRED",
                    reference_entity,
                    row.id,
                    {"reason": "current maximum transaction amount exceeded"},
                )
                continue

            if isinstance(row, Transfer):
                locked_wallets = db.scalars(
                    select(Wallet)
                    .where(Wallet.id.in_([row.sender_wallet_id, row.receiver_wallet_id]))
                    .order_by(Wallet.id)
                    .with_for_update()
                ).all()
                wallet_map = {wallet.id: wallet for wallet in locked_wallets}
                sender = wallet_map.get(row.sender_wallet_id)
                receiver = wallet_map.get(row.receiver_wallet_id)
                wallets = [wallet for wallet in (sender, receiver) if wallet is not None]
            else:
                wallet = db.scalar(
                    select(Wallet).where(Wallet.id == row.wallet_id).with_for_update()
                )
                wallets = [wallet] if wallet is not None else []

            allowed, reason = _retry_is_allowed(
                row,
                wallets,
                expected_wallet_count=2 if isinstance(row, Transfer) else 1,
            )
            if not allowed:
                _audit_system_event(
                    db,
                    "TRANSACTION_RETRY_DEFERRED",
                    reference_entity,
                    row.id,
                    {"reason": reason},
                )
                continue

            if isinstance(row, Deposit):
                wallet = wallets[0]
                before = wallet.available_balance
                wallet.available_balance += row.amount
                db.add(
                    LedgerEntry(
                        wallet_id=wallet.id,
                        transaction_type=LedgerType.DEPOSIT,
                        amount=row.amount,
                        balance_before=before,
                        balance_after=wallet.available_balance,
                        reference_entity="DEPOSIT",
                        reference_id=row.id,
                        created_by=row.user_id,
                        description="Retried deposit",
                    )
                )
            elif isinstance(row, Withdrawal):
                wallet = wallets[0]
                if wallet.available_balance < row.amount:
                    _audit_system_event(
                        db,
                        "TRANSACTION_RETRY_DEFERRED",
                        reference_entity,
                        row.id,
                        {"reason": "insufficient balance"},
                    )
                    continue
                before = wallet.available_balance
                wallet.available_balance -= row.amount
                db.add(
                    LedgerEntry(
                        wallet_id=wallet.id,
                        transaction_type=LedgerType.WITHDRAWAL,
                        amount=row.amount,
                        balance_before=before,
                        balance_after=wallet.available_balance,
                        reference_entity="WITHDRAWAL",
                        reference_id=row.id,
                        created_by=row.user_id,
                        description="Retried withdrawal",
                    )
                )
            else:
                sender = wallet_map[row.sender_wallet_id]
                receiver = wallet_map[row.receiver_wallet_id]
                if sender.available_balance < row.amount:
                    _audit_system_event(
                        db,
                        "TRANSACTION_RETRY_DEFERRED",
                        reference_entity,
                        row.id,
                        {"reason": "insufficient balance"},
                    )
                    continue
                sender_before, receiver_before = sender.available_balance, receiver.available_balance
                sender.available_balance -= row.amount
                receiver.available_balance += row.amount
                db.add_all(
                    [
                        LedgerEntry(
                            wallet_id=sender.id,
                            transaction_type=LedgerType.TRANSFER_DEBIT,
                            amount=row.amount,
                            balance_before=sender_before,
                            balance_after=sender.available_balance,
                            reference_entity="TRANSFER",
                            reference_id=row.id,
                            created_by=row.user_id,
                            description="Retried transfer sent",
                        ),
                        LedgerEntry(
                            wallet_id=receiver.id,
                            transaction_type=LedgerType.TRANSFER_CREDIT,
                            amount=row.amount,
                            balance_before=receiver_before,
                            balance_after=receiver.available_balance,
                            reference_entity="TRANSFER",
                            reference_id=row.id,
                            created_by=row.user_id,
                            description="Retried transfer received",
                        ),
                    ]
                )
            row.status = OperationStatus.COMPLETED
            row.completed_at = utcnow()
            completion_event = f"{row.__class__.__name__.upper()}_COMPLETED"
            _notify(
                db,
                row.user_id,
                completion_event,
                f"Your {row.__class__.__name__.lower()} {row.reference} was successfully retried.",
            )
            if isinstance(row, Transfer):
                _notify(
                    db,
                    receiver.owner_id,
                    "TRANSFER_RECEIVED",
                    f"Received {row.amount} {row.currency} from a retried transfer.",
                )
            _audit_system_event(
                db,
                completion_event,
                reference_entity,
                row.id,
                {"status": OperationStatus.COMPLETED.value, "retried": True},
            )
            retried += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return retried


run = retry_failed_transactions
