from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.constants import LedgerType, OperationStatus, RefundStatus


class TransactionOut(BaseModel):
    id: int
    wallet_id: int
    transaction_type: LedgerType
    amount: Decimal
    balance_before: Decimal | None
    balance_after: Decimal | None
    status: OperationStatus | RefundStatus | None = None
    reference_entity: str
    reference_id: int
    description: str
    created_by: int | None = None
    metadata_json: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class TransactionHistoryOut(BaseModel):
    items: list[TransactionOut]
    page: int
    page_size: int
    total: int


__all__ = ["TransactionHistoryOut", "TransactionOut"]
