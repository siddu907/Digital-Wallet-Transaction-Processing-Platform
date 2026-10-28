from app.core.security import hash_password, verify_password


def test_password_hash_is_not_plaintext_and_verifies():
    encoded = hash_password("SecureTest123!")
    assert encoded != "SecureTest123!"
    assert verify_password("SecureTest123!", encoded)
    assert not verify_password("wrong", encoded)
