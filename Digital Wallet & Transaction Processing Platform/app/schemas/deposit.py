from pydantic import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal
from app.core.constants import OperationStatus


class DepositOut(BaseModel):
    id: int
    wallet_id: int
    amount: Decimal
    currency: str
    status: OperationStatus
    reference: str
    created_at: datetime
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


__all__ = ["DepositOut"]
