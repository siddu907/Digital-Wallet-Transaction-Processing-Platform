from datetime import date

from sqlalchemy.orm import Session

from app.models import DailyLimitReset


class DailyLimitResetRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, reset_date: date) -> DailyLimitReset | None:
        return self.session.get(DailyLimitReset, reset_date)

    def add(self, reset_date: date) -> DailyLimitReset:
        record = DailyLimitReset(reset_date=reset_date)
        self.session.add(record)
        self.session.flush()
        return record
