from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Transfer, Wallet


class TransferRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, transfer_id: int, *, lock: bool = False) -> Transfer | None:
        query = select(Transfer).where(Transfer.id == transfer_id)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def for_user(self, user_id: int, *, page: int = 1, page_size: int = 20) -> list[Transfer]:
        receiver_wallets = select(Wallet.id).where(Wallet.owner_id == user_id)
        query = (
            select(Transfer)
            .where(or_(Transfer.user_id == user_id, Transfer.receiver_wallet_id.in_(receiver_wallets)))
            .order_by(Transfer.created_at.desc())
        )
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def list(self, *, user_id: int | None = None, page: int = 1, page_size: int = 20) -> list[Transfer]:
        query = select(Transfer).order_by(Transfer.created_at.desc())
        if user_id is not None:
            receiver_wallets = select(Wallet.id).where(Wallet.owner_id == user_id)
            query = query.where(
                or_(
                    Transfer.user_id == user_id,
                    Transfer.receiver_wallet_id.in_(receiver_wallets),
                )
            )
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))
