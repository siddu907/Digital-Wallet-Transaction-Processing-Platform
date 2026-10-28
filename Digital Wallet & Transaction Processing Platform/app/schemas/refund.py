from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import RefundStatus


class RefundCreate(BaseModel):
    ledger_entry_id: int = Field(
        description="ID of the sender's TRANSFER_DEBIT ledger entry for the outgoing transfer."
    )
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reason: str = Field(default="", max_length=255)


class RefundOut(BaseModel):
    id: int
    ledger_entry_id: int
    wallet_id: int
    amount: Decimal
    status: RefundStatus
    reason: str
    created_at: datetime
    reviewed_at: datetime | None = None
    completed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


__all__ = ["RefundCreate", "RefundOut"]
