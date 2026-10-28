from pydantic import BaseModel, Field
from decimal import Decimal


class LimitsPatch(BaseModel):
    max_transaction_amount: Decimal | None = Field(default=None, gt=0)
    daily_transfer_limit: Decimal | None = Field(default=None, gt=0)
    daily_withdrawal_limit: Decimal | None = Field(default=None, gt=0)
    max_transactions_per_day: int | None = Field(default=None, gt=0)
    suspicious_amount_threshold: Decimal | None = Field(default=None, gt=0)
