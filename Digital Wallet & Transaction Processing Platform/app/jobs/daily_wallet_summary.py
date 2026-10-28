from datetime import datetime

from sqlalchemy.orm import Session

from app.models import utcnow
from app.services.daily_summary_service import (
    create_daily_wallet_summary as build_daily_wallet_summary,
)


def create_daily_wallet_summary(db: Session, day: datetime | None = None) -> int:
    return build_daily_wallet_summary(db, (day or utcnow()).date())


run = create_daily_wallet_summary


