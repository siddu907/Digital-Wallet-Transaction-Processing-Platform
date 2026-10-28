from datetime import datetime

from sqlalchemy.orm import Session

from app.services.report_service import daily_transaction_report as build_daily_transaction_report


def daily_transaction_report(db: Session, day: datetime | None = None) -> dict:
    return build_daily_transaction_report(db, day)


run = daily_transaction_report


