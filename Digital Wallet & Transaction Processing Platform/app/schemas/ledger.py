from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.core.constants import LedgerType


class LedgerOut(BaseModel):
    id: int
    wallet_id: int
    transaction_type: LedgerType
    amount: Decimal
    balance_before: Decimal
    balance_after: Decimal
    reference_entity: str
    reference_id: int
    description: str
    created_by: int | None
    metadata_json: dict
    created_at: datetime


__all__ = ["LedgerOut"]
