from fastapi import HTTPException
from sqlalchemy import select
from app.core.exceptions import DomainError
from app.models import Role, User

staff_roles = (Role.SUPER_ADMIN, Role.ADMIN, Role.SUPPORT_AGENT)
admin_roles = (Role.SUPER_ADMIN, Role.ADMIN)

def _staff(user: User) -> bool:
    return user.role in staff_roles

def _owned_or_staff(owner_id: int, user: User) -> None:
    if owner_id != user.id and not _staff(user):
        raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)

def _page(query, page: int, page_size: int):
    return query.offset((page - 1) * page_size).limit(page_size)

def _idempotency(value: str | None) -> str:
    if not value or len(value) > 128 or not value.strip():
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "Provide a valid Idempotency-Key header.", 400)
    return value.strip()
