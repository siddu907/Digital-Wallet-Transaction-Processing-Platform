from app.schemas import LimitsPatch


def test_transaction_limits_require_positive_values():
    assert LimitsPatch(max_transaction_amount="10.00").max_transaction_amount > 0
