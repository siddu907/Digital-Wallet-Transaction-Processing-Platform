import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import DateTime, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models._timestamps import utcnow
from app.core.constants import OperationStatus


class FinancialOperation(Base):
    __abstract__ = True
    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[OperationStatus] = mapped_column(Enum(OperationStatus), default=OperationStatus.COMPLETED)
    reference: Mapped[str] = mapped_column(String(64), unique=True, default=lambda: uuid.uuid4().hex)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
