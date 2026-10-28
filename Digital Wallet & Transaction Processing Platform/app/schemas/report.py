from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DailyReport(BaseModel):
    date: date
    transactions: int
    volume: Decimal
