from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class WalletBalance(BaseModel):
    available_balance: Decimal
    pending_balance: Decimal

    model_config = ConfigDict(from_attributes=True)


__all__ = ["WalletBalance"]
