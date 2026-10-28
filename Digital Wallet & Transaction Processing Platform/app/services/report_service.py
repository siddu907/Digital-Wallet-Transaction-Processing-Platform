from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import utcnow
from app.repositories.report_repository import ReportRepository


def daily_transaction_report(db: Session, day: datetime | None = None) -> dict:
    start = (day or utcnow()).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    transactions, volume = ReportRepository(db).daily_operation_totals(start, end)
    return {"date": start.date().isoformat(), "transactions": transactions, "volume": volume}
