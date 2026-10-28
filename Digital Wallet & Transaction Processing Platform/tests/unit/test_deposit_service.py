from decimal import Decimal

from app.services.financial_common import ZERO


def test_money_uses_decimal_precision():
    assert Decimal("0.10") + Decimal("0.20") == Decimal("0.30")
    assert ZERO == Decimal("0.00")
