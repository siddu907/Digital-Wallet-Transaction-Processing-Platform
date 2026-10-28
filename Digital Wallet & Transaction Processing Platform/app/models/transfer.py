from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.constants import RiskStatus
from app.models.transaction import FinancialOperation
from app.models._timestamps import utcnow


class Transfer(FinancialOperation):
    __tablename__ = "transfers"
    sender_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="RESTRICT"), index=True)
    receiver_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="RESTRICT"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    risk_status: Mapped[RiskStatus] = mapped_column(Enum(RiskStatus), default=RiskStatus.NORMAL)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
