from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Wallet


class WalletRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, wallet_id: int, *, lock: bool = False) -> Wallet | None:
        query = select(Wallet).where(Wallet.id == wallet_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def for_owner(self, owner_id: int) -> list[Wallet]:
        query = select(Wallet).where(Wallet.owner_id == owner_id).order_by(Wallet.created_at.desc())
        return list(self.session.scalars(query))

    def get_many(self, wallet_ids: list[str], *, lock: bool = False) -> list[Wallet]:
        query = select(Wallet).where(Wallet.id.in_(wallet_ids)).order_by(Wallet.id)
        if lock:
            query = query.with_for_update()
        return list(self.session.scalars(query))

    def get_many_for_transfer(self, sender_id: int, receiver_id: int) -> list[Wallet]:
        return self.get_many([sender_id, receiver_id], lock=True)

    def list(self, *, owner_id: int | None = None) -> list[Wallet]:
        query = select(Wallet).order_by(Wallet.created_at.desc())
        if owner_id is not None:
            query = query.where(Wallet.owner_id == owner_id)
        return list(self.session.scalars(query))

    def all_for_update(self) -> list[Wallet]:
        return list(
            self.session.scalars(
                select(Wallet).order_by(Wallet.id).with_for_update()
            )
        )

    def add(self, wallet: Wallet) -> Wallet:
        self.session.add(wallet)
        self.session.flush()
        return wallet
