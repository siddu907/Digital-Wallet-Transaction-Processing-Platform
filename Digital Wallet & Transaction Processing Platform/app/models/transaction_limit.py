from decimal import Decimal
from sqlalchemy import Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class TransactionLimit(Base):
    __tablename__ = "transaction_limits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_transaction_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("100000"))
    daily_transfer_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("200000"))
    daily_withdrawal_limit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("50000"))
    max_transactions_per_day: Mapped[int] = mapped_column(Integer, default=100)
    suspicious_amount_threshold: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("50000"))
