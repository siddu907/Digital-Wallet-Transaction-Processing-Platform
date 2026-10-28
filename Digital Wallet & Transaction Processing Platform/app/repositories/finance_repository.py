from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import IdempotencyKey, LedgerEntry, LedgerType, TransactionLimit, User, Wallet


class FinanceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_wallet(self, wallet_id: int, *, lock: bool = False) -> Wallet | None:
        query = select(Wallet).where(Wallet.id == wallet_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def get_limits_for_update(self) -> TransactionLimit | None:
        return self.session.scalar(select(TransactionLimit).where(TransactionLimit.id == 1).with_for_update())

    def get_idempotency_key(self, user_id: int, key: str) -> IdempotencyKey | None:
        return self.session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.user_id == user_id, IdempotencyKey.key == key)
        )

    def lock_user(self, user_id: int) -> User | None:
        return self.session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )

    def count_user_operations(self, user_id: int, start, models: tuple) -> int:
        return sum(
            self.session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.user_id == user_id, model.created_at >= start)
            )
            or 0
            for model in models
        )

    def sum_user_operation_amount(self, user_id: int, start, model) -> Decimal:
        value = self.session.scalar(
            select(func.coalesce(func.sum(model.amount), 0)).where(
                model.user_id == user_id,
                model.created_at >= start,
            )
        )
        return Decimal(value or 0)

    def get_entity(self, model, entity_id: int):
        return self.session.get(model, entity_id)

    def append_ledger(
        self,
        wallet: Wallet,
        kind: LedgerType,
        amount: Decimal,
        before: Decimal,
        reference_entity: str,
        reference_id: int,
        user: User | None,
        description: str,
    ) -> LedgerEntry:
        entry = LedgerEntry(
            wallet_id=wallet.id,
            transaction_type=kind,
            amount=amount,
            balance_before=before,
            balance_after=wallet.available_balance,
            reference_entity=reference_entity,
            reference_id=reference_id,
            created_by=user.id if user is not None else None,
            description=description,
        )
        self.session.add(entry)
        return entry
