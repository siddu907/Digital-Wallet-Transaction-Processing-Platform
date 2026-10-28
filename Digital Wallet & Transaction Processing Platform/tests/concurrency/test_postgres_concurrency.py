import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import create_engine, delete, func, select, text, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError
from sqlalchemy.engine import make_url

from app import models
from app.database import Base
from app.services.deposit_service import create_deposit
from app.services.transfer_service import create_transfer
from app.services.withdrawal_service import create_withdrawal

DATABASE_URL = os.getenv("TEST_DATABASE_URL")
IS_POSTGRESQL = bool(
    DATABASE_URL and make_url(DATABASE_URL).get_backend_name() == "postgresql"
)
pytestmark = pytest.mark.skipif(not IS_POSTGRESQL, reason="Set TEST_DATABASE_URL to a dedicated PostgreSQL test database.")


def _drop_ledger_guards(db) -> bool:
    if db.bind.dialect.name != "postgresql":
        return False
    guard_exists = db.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_trigger
                WHERE tgname IN (
                    'transaction_ledger_no_update_delete',
                    'transaction_ledger_no_truncate'
                )
                AND NOT tgisinternal
            )
            """
        )
    )
    if guard_exists:
        db.execute(text("DROP TRIGGER IF EXISTS transaction_ledger_no_truncate ON transaction_ledger"))
        db.execute(text("DROP TRIGGER IF EXISTS transaction_ledger_no_update_delete ON transaction_ledger"))
    return bool(guard_exists)


def _restore_ledger_guards(db, restore: bool) -> None:
    if restore:
        db.execute(
            text(
                """
                CREATE TRIGGER transaction_ledger_no_update_delete
                BEFORE UPDATE OR DELETE ON transaction_ledger
                FOR EACH ROW EXECUTE FUNCTION reject_transaction_ledger_mutation()
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TRIGGER transaction_ledger_no_truncate
                BEFORE TRUNCATE ON transaction_ledger
                FOR EACH STATEMENT EXECUTE FUNCTION reject_transaction_ledger_mutation()
                """
            )
        )


def _drop_audit_guards(db) -> bool:
    if db.bind.dialect.name != "postgresql":
        return False
    guard_exists = db.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_trigger
                WHERE tgname IN ('audit_logs_no_update_delete', 'audit_logs_no_truncate')
                AND NOT tgisinternal
            )
            """
        )
    )
    if guard_exists:
        db.execute(text("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs"))
        db.execute(text("DROP TRIGGER IF EXISTS audit_logs_no_update_delete ON audit_logs"))
    return bool(guard_exists)


def _restore_audit_guards(db, restore: bool) -> None:
    if restore:
        db.execute(
            text(
                """
                CREATE TRIGGER audit_logs_no_update_delete
                BEFORE UPDATE OR DELETE ON audit_logs
                FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()
                """
            )
        )
        db.execute(
            text(
                """
                CREATE TRIGGER audit_logs_no_truncate
                BEFORE TRUNCATE ON audit_logs
                FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_log_mutation()
                """
            )
        )


@pytest.mark.parametrize("operation", ["transfer", "withdrawal", "idempotent-transfer"])
def test_parallel_debits_do_not_overspend(operation):
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=5)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    unique = uuid.uuid4().hex
    user_id = None
    receiver_ids = []
    sender_wallet_id = None
    receiver_wallet_ids = []
    try:
        with Session() as db:
            if db.get(models.TransactionLimit, 1) is None:
                db.add(models.TransactionLimit(id=1))
            sender = models.User(email=f"sender-{unique}@test.invalid", full_name="Concurrent Sender", password_hash="unused")
            receivers = [
                models.User(
                    email=f"receiver-{unique}-{index}@test.invalid",
                    full_name="Concurrent Receiver",
                    password_hash="unused",
                )
                for index in range(2)
            ]
            db.add_all([sender, *receivers])
            db.flush()
            user_id = sender.id
            receiver_ids = [receiver.id for receiver in receivers]
            sender_wallet = models.Wallet(owner_id=user_id, currency="INR", available_balance=Decimal("1000.00"))
            receiver_wallets = [
                models.Wallet(owner_id=owner_id, currency="INR")
                for owner_id in receiver_ids
            ]
            db.add_all([sender_wallet, *receiver_wallets])
            db.flush()
            sender_wallet_id = sender_wallet.id
            receiver_wallet_ids = [wallet.id for wallet in receiver_wallets]
            db.commit()

        def request(amount: str, index: int) -> str:
            with Session() as db:
                user = db.get(models.User, user_id)
                try:
                    if operation == "transfer":
                        result = create_transfer(db, user, sender_wallet_id, receiver_wallet_ids[index], Decimal(amount), f"{unique}-{index}")
                    elif operation == "idempotent-transfer":
                        result = create_transfer(db, user, sender_wallet_id, receiver_wallet_ids[0], Decimal("300.00"), f"{unique}-same")
                    else:
                        result = create_withdrawal(db, user, sender_wallet_id, Decimal(amount), f"{unique}-{index}")
                    return f"completed:{result.id}"
                except Exception as exc:
                    if getattr(exc, "code", None) == "INSUFFICIENT_BALANCE":
                        return "insufficient"
                    raise

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda args: request(*args), [("800.00", 0), ("700.00", 1)]))
        completed = [result for result in outcomes if result.startswith("completed:")]
        if operation == "idempotent-transfer":
            assert len(completed) == 2
            assert completed[0] == completed[1]
        else:
            assert len(completed) == 1
            assert outcomes.count("insufficient") == 1
        with Session() as db:
            sender_balance = db.scalar(select(models.Wallet.available_balance).where(models.Wallet.id == sender_wallet_id))
            if operation == "idempotent-transfer":
                assert sender_balance == Decimal("700.00")
            else:
                assert sender_balance in {Decimal("200.00"), Decimal("300.00")}
            if operation == "transfer":
                total_received = db.scalar(select(func.coalesce(func.sum(models.Wallet.available_balance), 0)).where(models.Wallet.id.in_(receiver_wallet_ids)))
                assert Decimal(total_received) == Decimal("1000.00") - Decimal(sender_balance)
            if operation == "idempotent-transfer":
                received = db.scalar(select(models.Wallet.available_balance).where(models.Wallet.id == receiver_wallet_ids[0]))
                assert received == Decimal("300.00")
    finally:
        with Session() as db:
            restore_ledger_guards = _drop_ledger_guards(db)
            restore_audit_guards = _drop_audit_guards(db)
            db.execute(delete(models.LedgerEntry).where(models.LedgerEntry.wallet_id.in_([sender_wallet_id, *receiver_wallet_ids])))
            db.execute(delete(models.Transfer).where(models.Transfer.user_id == user_id))
            db.execute(delete(models.Withdrawal).where(models.Withdrawal.user_id == user_id))
            db.execute(delete(models.Deposit).where(models.Deposit.user_id == user_id))
            db.execute(delete(models.IdempotencyKey).where(models.IdempotencyKey.user_id == user_id))
            db.execute(delete(models.Notification).where(models.Notification.user_id.in_([user_id, *receiver_ids])))
            db.execute(delete(models.AuditLog).where(models.AuditLog.user_id == user_id))
            db.execute(delete(models.Wallet).where(models.Wallet.id.in_([sender_wallet_id, *receiver_wallet_ids])))
            db.execute(delete(models.User).where(models.User.id.in_([user_id, *receiver_ids])))
            _restore_ledger_guards(db, restore_ledger_guards)
            _restore_audit_guards(db, restore_audit_guards)
            db.commit()
        engine.dispose()


def test_concurrent_deposits_cannot_exceed_daily_transaction_count():
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=5)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    unique = uuid.uuid4().hex
    user_id = None
    wallet_ids = []
    previous_max_count = None
    try:
        with Session() as db:
            limits = db.get(models.TransactionLimit, 1)
            if limits is None:
                limits = models.TransactionLimit(id=1)
                db.add(limits)
                db.flush()
            previous_max_count = limits.max_transactions_per_day
            limits.max_transactions_per_day = 1
            db.add(
                models.User(
                    email=f"daily-limit-{unique}@test.invalid",
                    full_name="Daily Limit",
                    password_hash="unused",
                )
            )
            db.flush()
            user_id = db.scalar(
                select(models.User.id).where(
                    models.User.email == f"daily-limit-{unique}@test.invalid"
                )
            )
            wallets = [
                models.Wallet(owner_id=user_id, currency="INR"),
                models.Wallet(owner_id=user_id, currency="USD"),
            ]
            db.add_all(
                wallets
            )
            db.flush()
            wallet_ids = [wallet.id for wallet in wallets]
            db.commit()

        def create(index: int) -> str:
            with Session() as db:
                user = db.get(models.User, user_id)
                try:
                    result = create_deposit(
                        db,
                        user,
                        wallet_ids[index],
                        Decimal("10.00"),
                        f"{unique}-{index}",
                    )
                    return f"completed:{result.id}"
                except Exception as exc:
                    if getattr(exc, "code", None) == "TRANSACTION_LIMIT_EXCEEDED":
                        return "limit-exceeded"
                    raise

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(create, [0, 1]))
        assert sum(result.startswith("completed:") for result in outcomes) == 1
        assert outcomes.count("limit-exceeded") == 1
        with Session() as db:
            deposits = db.scalar(
                select(func.count())
                .select_from(models.Deposit)
                .where(models.Deposit.user_id == user_id)
            )
            assert deposits == 1
    finally:
        with Session() as db:
            restore_ledger_guards = _drop_ledger_guards(db)
            restore_audit_guards = _drop_audit_guards(db)
            db.execute(delete(models.LedgerEntry).where(models.LedgerEntry.wallet_id.in_(wallet_ids)))
            db.execute(delete(models.Deposit).where(models.Deposit.user_id == user_id))
            db.execute(delete(models.IdempotencyKey).where(models.IdempotencyKey.user_id == user_id))
            db.execute(delete(models.Notification).where(models.Notification.user_id == user_id))
            db.execute(delete(models.AuditLog).where(models.AuditLog.user_id == user_id))
            db.execute(delete(models.Wallet).where(models.Wallet.id.in_(wallet_ids)))
            db.execute(delete(models.User).where(models.User.id == user_id))
            if previous_max_count is not None:
                limits = db.get(models.TransactionLimit, 1)
                if limits is not None:
                    limits.max_transactions_per_day = previous_max_count
            _restore_ledger_guards(db, restore_ledger_guards)
            _restore_audit_guards(db, restore_audit_guards)
            db.commit()
        engine.dispose()


def test_postgresql_ledger_rejects_updates_and_deletes():
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    unique = uuid.uuid4().hex
    user_id = None
    wallet_id = None
    ledger_id = None
    try:
        with engine.connect() as connection:
            has_guard = connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'transaction_ledger_no_update_delete'
                        AND NOT tgisinternal
                    )
                    """
                )
            )
        if not has_guard:
            pytest.skip("Apply Alembic migrations through 0004_immutable_ledger.")

        with Session() as db:
            db.add(
                models.User(
                    email=f"immutable-ledger-{unique}@test.invalid",
                    full_name="Immutable Ledger",
                    password_hash="unused",
                )
            )
            db.flush()
            user_id = db.scalar(
                select(models.User.id).where(
                    models.User.email == f"immutable-ledger-{unique}@test.invalid"
                )
            )
            wallet = models.Wallet(
                owner_id=user_id,
                currency="INR",
                available_balance=Decimal("1.00"),
            )
            db.add(wallet)
            db.flush()
            wallet_id = wallet.id
            ledger = models.LedgerEntry(
                wallet_id=wallet_id,
                transaction_type=models.LedgerType.DEPOSIT,
                amount=Decimal("1.00"),
                balance_before=Decimal("0.00"),
                balance_after=Decimal("1.00"),
                reference_entity="TEST",
                reference_id=1,
                created_by=user_id,
                description="Immutable ledger test",
            )
            db.add(ledger)
            db.flush()
            ledger_id = ledger.id
            db.commit()

        with engine.connect() as connection:
            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    update(models.LedgerEntry)
                    .where(models.LedgerEntry.id == ledger_id)
                    .values(description="tampered")
                )
            transaction.rollback()

            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    delete(models.LedgerEntry).where(
                        models.LedgerEntry.id == ledger_id
                    )
                )
            transaction.rollback()
    finally:
        with Session() as db:
            restore_ledger_guards = _drop_ledger_guards(db)
            restore_audit_guards = _drop_audit_guards(db)
            db.execute(delete(models.LedgerEntry).where(models.LedgerEntry.id == ledger_id))
            db.execute(delete(models.Wallet).where(models.Wallet.id == wallet_id))
            db.execute(delete(models.User).where(models.User.id == user_id))
            _restore_ledger_guards(db, restore_ledger_guards)
            _restore_audit_guards(db, restore_audit_guards)
            db.commit()
        engine.dispose()


def test_postgresql_audit_logs_reject_updates_deletes_and_truncates():
    assert DATABASE_URL
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    unique = uuid.uuid4().hex
    user_id = None
    audit_id = None
    try:
        with engine.connect() as connection:
            has_guard = connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_trigger
                        WHERE tgname = 'audit_logs_no_update_delete'
                        AND NOT tgisinternal
                    )
                    """
                )
            )
        if not has_guard:
            pytest.skip("Apply Alembic migrations through 0005_immutable_audit_logs.")

        with Session() as db:
            db.add(
                models.User(
                    email=f"immutable-audit-{unique}@test.invalid",
                    full_name="Immutable Audit",
                    password_hash="unused",
                )
            )
            db.flush()
            user_id = db.scalar(
                select(models.User.id).where(
                    models.User.email == f"immutable-audit-{unique}@test.invalid"
                )
            )
            audit = models.AuditLog(
                user_id=user_id,
                action="TEST",
                entity="TEST",
                entity_id=1,
                metadata_json={},
            )
            db.add(audit)
            db.flush()
            audit_id = audit.id
            db.commit()

        with engine.connect() as connection:
            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    update(models.AuditLog)
                    .where(models.AuditLog.id == audit_id)
                    .values(action="TAMPERED")
                )
            transaction.rollback()

            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    delete(models.AuditLog).where(models.AuditLog.id == audit_id)
                )
            transaction.rollback()

            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(text("TRUNCATE TABLE audit_logs"))
            transaction.rollback()

            transaction = connection.begin()
            with pytest.raises(DBAPIError):
                connection.execute(
                    delete(models.User).where(models.User.id == user_id)
                )
            transaction.rollback()
    finally:
        with Session() as db:
            restore_audit_guards = _drop_audit_guards(db)
            db.execute(delete(models.AuditLog).where(models.AuditLog.id == audit_id))
            db.execute(delete(models.User).where(models.User.id == user_id))
            _restore_audit_guards(db, restore_audit_guards)
            db.commit()
        engine.dispose()
