from pydantic import BaseModel, Field
from decimal import Decimal


class AmountRequest(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
