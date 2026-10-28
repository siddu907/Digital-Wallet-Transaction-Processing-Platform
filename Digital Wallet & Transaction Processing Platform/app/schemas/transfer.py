from app.schemas.common import AmountRequest
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal
from app.core.constants import OperationStatus


class TransferCreate(AmountRequest):
    sender_wallet_id: int
    receiver_wallet_id: int


class TransferOut(BaseModel):
    id: int
    sender_wallet_id: int
    receiver_wallet_id: int
    amount: Decimal
    currency: str
    status: OperationStatus
    reference: str
    created_at: datetime
    completed_at: datetime | None
    reversed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


__all__ = ["TransferCreate", "TransferOut"]
