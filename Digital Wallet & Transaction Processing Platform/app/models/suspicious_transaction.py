from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models._timestamps import utcnow
from app.core.constants import RiskStatus


class SuspiciousTransaction(Base):
    __tablename__ = "suspicious_transactions"
    __table_args__ = (
        UniqueConstraint(
            "operation_type",
            "operation_id",
            name="uq_suspicious_operation",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_id: Mapped[int | None] = mapped_column(ForeignKey("transfers.id", ondelete="RESTRICT"), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    wallet_id: Mapped[int | None] = mapped_column(ForeignKey("wallets.id", ondelete="SET NULL"), index=True)
    operation_type: Mapped[str | None] = mapped_column(String(32))
    operation_id: Mapped[int | None] = mapped_column()
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    status: Mapped[RiskStatus] = mapped_column(Enum(RiskStatus), default=RiskStatus.REVIEW_REQUIRED)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
