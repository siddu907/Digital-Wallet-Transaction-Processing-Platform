from app.services.idempotency_service import _fingerprint


def test_request_fingerprint_is_order_independent():
    assert _fingerprint({"amount": "10", "wallet": "id"}) == _fingerprint({"wallet": "id", "amount": "10"})
