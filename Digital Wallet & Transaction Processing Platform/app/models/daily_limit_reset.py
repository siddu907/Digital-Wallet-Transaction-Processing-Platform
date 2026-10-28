from datetime import date, datetime

from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models._timestamps import utcnow


class DailyLimitReset(Base):
    __tablename__ = "daily_limit_resets"

    reset_date: Mapped[date] = mapped_column(Date, primary_key=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(
        String(32),
        default="UTC_CALENDAR_DAY",
        nullable=False,
    )
