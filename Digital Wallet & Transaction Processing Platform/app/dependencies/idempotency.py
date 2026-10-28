from fastapi import Header

from app.core.exceptions import DomainError


def require_idempotency_key(value: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if not value or len(value) > 128 or not value.strip():
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Provide a valid Idempotency-Key header.", 400)
    return value.strip()
