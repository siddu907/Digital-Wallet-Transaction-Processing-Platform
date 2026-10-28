from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LedgerEntry, LedgerType


class LedgerRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, entry_id: int, *, lock: bool = False) -> LedgerEntry | None:
        query = select(LedgerEntry).where(LedgerEntry.id == entry_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def by_reference(self, entity: str, reference_id: int) -> LedgerEntry | None:
        return self.session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.reference_entity == entity,
                LedgerEntry.reference_id == reference_id,
                LedgerEntry.transaction_type == LedgerType.REFUND,
            )
        )

    def transfer_debit(self, transfer_id: int, *, lock: bool = False) -> LedgerEntry | None:
        query = select(LedgerEntry).where(
            LedgerEntry.reference_entity == "TRANSFER",
            LedgerEntry.reference_id == transfer_id,
            LedgerEntry.transaction_type == LedgerType.TRANSFER_DEBIT,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def for_wallet(self, wallet_id: int, *, page: int = 1, page_size: int = 20) -> list[LedgerEntry]:
        query = (
            select(LedgerEntry)
            .where(LedgerEntry.wallet_id == wallet_id)
            .order_by(LedgerEntry.created_at.desc())
        )
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def list(self, *, owner_id: int | None = None, page: int = 1, page_size: int = 20) -> list[LedgerEntry]:
        query = select(LedgerEntry).order_by(LedgerEntry.created_at.desc())
        if owner_id is not None:
            from app.models import Wallet

            query = query.where(
                LedgerEntry.wallet_id.in_(
                    select(Wallet.id).where(Wallet.owner_id == owner_id)
                )
            )
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))
