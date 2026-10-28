from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.transaction import FinancialOperation


class Withdrawal(FinancialOperation):
    __tablename__ = "withdrawals"
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
