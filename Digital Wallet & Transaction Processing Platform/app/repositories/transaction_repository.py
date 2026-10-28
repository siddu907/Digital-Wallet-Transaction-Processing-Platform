from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import (
    JSON,
    Numeric,
    String,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import Session

from app.models import (
    Deposit,
    LedgerEntry,
    Refund,
    Transfer,
    Wallet,
    Withdrawal,
)


class TransactionRepository:
    operation_models = (Deposit, Transfer, Withdrawal)

    def __init__(self, session: Session):
        self.session = session

    def by_reference(self, entity: str, reference_id: int):
        model = {
            "DEPOSIT": Deposit,
            "TRANSFER": Transfer,
            "WITHDRAWAL": Withdrawal,
            "REFUND": Refund,
        }.get(entity)
        if model is None:
            return None
        return self.session.scalar(select(model).where(model.id == reference_id))

    def transaction_history(
        self,
        *,
        user_id: int | None,
        page: int,
        page_size: int,
        transaction_kinds: list[str] | None,
        status: str | None,
        minimum_amount,
        maximum_amount,
        from_date: date | None,
        to_date: date | None,
        search: str | None,
        sort_by: str,
        sort_order: str,
    ) -> dict:
        if sort_by not in {"created_at", "amount"}:
            raise ValueError(f"Unsupported transaction sort column: {sort_by}")

        ledger_status = case(
            (
                LedgerEntry.reference_entity == "DEPOSIT",
                select(cast(Deposit.status, type_=String))
                .where(Deposit.id == LedgerEntry.reference_id)
                .scalar_subquery(),
            ),
            (
                LedgerEntry.reference_entity == "TRANSFER",
                select(cast(Transfer.status, type_=String))
                .where(Transfer.id == LedgerEntry.reference_id)
                .scalar_subquery(),
            ),
            (
                LedgerEntry.reference_entity == "WITHDRAWAL",
                select(cast(Withdrawal.status, type_=String))
                .where(Withdrawal.id == LedgerEntry.reference_id)
                .scalar_subquery(),
            ),
            (
                LedgerEntry.reference_entity == "REFUND",
                select(cast(Refund.status, type_=String))
                .where(Refund.id == LedgerEntry.reference_id)
                .scalar_subquery(),
            ),
            else_=None,
        )
        ledger_entries = select(
            LedgerEntry.id.label("id"),
            LedgerEntry.wallet_id.label("wallet_id"),
            cast(LedgerEntry.transaction_type, type_=String).label("transaction_type"),
            LedgerEntry.amount.label("amount"),
            LedgerEntry.balance_before.label("balance_before"),
            LedgerEntry.balance_after.label("balance_after"),
            ledger_status.label("status"),
            LedgerEntry.reference_entity.label("reference_entity"),
            LedgerEntry.reference_id.label("reference_id"),
            LedgerEntry.description.label("description"),
            LedgerEntry.created_by.label("created_by"),
            LedgerEntry.metadata_json.label("metadata_json"),
            LedgerEntry.created_at.label("created_at"),
        )
        if user_id is not None:
            ledger_entries = ledger_entries.where(
                LedgerEntry.wallet_id.in_(
                    select(Wallet.id).where(Wallet.owner_id == user_id)
                )
            )
        entries = [ledger_entries]

        # Non-ledger states (pending, failed, rejected, or cancelled before posting)
        # must remain visible in transaction history as well.
        def has_no_ledger_entry(entity: str, model):
            return ~exists(
                select(LedgerEntry.id).where(
                    LedgerEntry.reference_entity == entity,
                    LedgerEntry.reference_id == model.id,
                )
            )

        def operation_projection(
            model,
            entity: str,
            kind: str,
            wallet_column,
            owner_predicate,
            description_column,
        ):
            statement = select(
                model.id.label("id"),
                wallet_column.label("wallet_id"),
                literal(kind).label("transaction_type"),
                model.amount.label("amount"),
                literal(None, type_=Numeric(18, 2)).label("balance_before"),
                literal(None, type_=Numeric(18, 2)).label("balance_after"),
                cast(model.status, type_=String).label("status"),
                literal(entity).label("reference_entity"),
                model.id.label("reference_id"),
                description_column.label("description"),
                model.user_id.label("created_by"),
                literal({}, type_=JSON).label("metadata_json"),
                model.created_at.label("created_at"),
            ).where(has_no_ledger_entry(entity, model))
            if owner_predicate is not None:
                statement = statement.where(owner_predicate)
            return statement

        kinds = set(transaction_kinds or ())
        include_all_kinds = transaction_kinds is None
        include_deposit = include_all_kinds or "DEPOSIT" in kinds
        include_withdrawal = include_all_kinds or "WITHDRAWAL" in kinds
        include_refund = include_all_kinds or "REFUND" in kinds
        include_transfer_debit = include_all_kinds or bool(
            kinds.intersection({"TRANSFER", "TRANSFER_DEBIT"})
        )
        include_transfer_credit = include_all_kinds or bool(
            kinds.intersection({"TRANSFER", "TRANSFER_CREDIT"})
        )

        if include_deposit:
            entries.append(
                operation_projection(
                    Deposit,
                    "DEPOSIT",
                    "DEPOSIT",
                    Deposit.wallet_id,
                    Deposit.user_id == user_id if user_id is not None else None,
                    literal("Deposit operation"),
                )
            )
        if include_withdrawal:
            entries.append(
                operation_projection(
                    Withdrawal,
                    "WITHDRAWAL",
                    "WITHDRAWAL",
                    Withdrawal.wallet_id,
                    Withdrawal.user_id == user_id if user_id is not None else None,
                    literal("Withdrawal operation"),
                )
            )
        if include_refund:
            entries.append(
                operation_projection(
                    Refund,
                    "REFUND",
                    "REFUND",
                    Refund.wallet_id,
                    Refund.user_id == user_id if user_id is not None else None,
                    Refund.reason,
                )
            )
        if include_transfer_debit:
            entries.append(
                operation_projection(
                    Transfer,
                    "TRANSFER",
                    "TRANSFER_DEBIT",
                    Transfer.sender_wallet_id,
                    Transfer.user_id == user_id if user_id is not None else None,
                    literal("Outgoing transfer"),
                )
            )
        if include_transfer_credit:
            receiver_owner = (
                select(Wallet.id)
                .where(Wallet.id == Transfer.receiver_wallet_id, Wallet.owner_id == user_id)
                .exists()
                if user_id is not None
                else None
            )
            entries.append(
                operation_projection(
                    Transfer,
                    "TRANSFER",
                    "TRANSFER_CREDIT",
                    Transfer.receiver_wallet_id,
                    receiver_owner,
                    literal("Incoming transfer"),
                )
            )

        normalized = union_all(*entries).subquery("transaction_history")
        query = select(normalized)
        if transaction_kinds is not None:
            query = query.where(normalized.c.transaction_type.in_(transaction_kinds))
        if status is not None:
            query = query.where(normalized.c.status == status)
        if minimum_amount is not None:
            query = query.where(normalized.c.amount >= minimum_amount)
        if maximum_amount is not None:
            query = query.where(normalized.c.amount <= maximum_amount)
        if from_date is not None:
            query = query.where(
                normalized.c.created_at
                >= datetime.combine(from_date, time.min, tzinfo=timezone.utc)
            )
        if to_date is not None:
            query = query.where(
                normalized.c.created_at
                < datetime.combine(
                    to_date + timedelta(days=1),
                    time.min,
                    tzinfo=timezone.utc,
                )
            )
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    cast(normalized.c.reference_id, String).ilike(pattern),
                    normalized.c.description.ilike(pattern),
                )
            )
        sort_column = getattr(normalized.c, sort_by)
        query = query.order_by(
            sort_column.desc() if sort_order == "desc" else sort_column.asc(),
            normalized.c.id.asc(),
            normalized.c.wallet_id.asc(),
        )
        total = self.session.scalar(
            select(func.count()).select_from(query.subquery())
        ) or 0
        items = self.session.execute(
            query.offset((page - 1) * page_size).limit(page_size)
        ).mappings().all()
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
        }

    def get_ledger_entry(self, transaction_id: int) -> LedgerEntry | None:
        return self.session.get(LedgerEntry, transaction_id)

    def get_unposted_operation(self, operation_id: int):
        for model in (Deposit, Transfer, Withdrawal, Refund):
            operation = self.session.scalar(
                select(model)
                .where(model.id == operation_id)
                .where(
                    ~exists(
                        select(LedgerEntry.id).where(
                            LedgerEntry.reference_entity == model.__tablename__.rstrip("s").upper(),
                            LedgerEntry.reference_id == model.id,
                        )
                    )
                )
            )
            if operation is not None:
                return operation
        return None

    def get_wallet(self, wallet_id: int, *, lock: bool = False) -> Wallet | None:
        query = select(Wallet).where(Wallet.id == wallet_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def get_operation(self, model, operation_id: int, *, lock: bool = False):
        query = select(model).where(model.id == operation_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def get_wallets(self, wallet_ids: list[int], *, lock: bool = False) -> list[Wallet]:
        query = select(Wallet).where(Wallet.id.in_(wallet_ids)).order_by(Wallet.id)
        if lock:
            query = query.with_for_update()
        return list(self.session.scalars(query))
