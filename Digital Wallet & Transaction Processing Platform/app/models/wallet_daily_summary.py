from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models._timestamps import utcnow


class WalletDailySummary(Base):
    __tablename__ = "wallet_daily_summaries"
    __table_args__ = (UniqueConstraint("wallet_id", "summary_date", name="uq_wallet_summary_day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True)
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pending_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
