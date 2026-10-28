from pydantic import BaseModel, Field, field_validator
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from decimal import Decimal
from app.core.constants import WalletStatus
from pydantic import BaseModel


class WalletCreate(BaseModel):
    currency: str = Field(default="INR", min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        value = value.upper()
        if not value.isalpha():
            raise ValueError("Currency must contain three letters.")
        return value


class WalletOut(BaseModel):
    id: int
    owner_id: int
    currency: str
    available_balance: Decimal
    pending_balance: Decimal
    status: WalletStatus
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WalletPatch(BaseModel):
    status: WalletStatus | None = None
