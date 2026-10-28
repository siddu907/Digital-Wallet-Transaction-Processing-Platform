from sqlalchemy.orm import Session

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import DomainError
from app.core.security import hash_password
from app.models import Role, User, utcnow
from app.repositories.user_repository import UserRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.audit_service import _audit


def create_user(
    db: Session,
    email: str,
    full_name: str,
    password: str,
    role: Role = Role.CUSTOMER,
) -> User:
    repository = UserRepository(db)
    normalized_email = email.lower()
    if repository.by_email(normalized_email):
        raise DomainError("DUPLICATE_USER", "An account with this email already exists.", 409)
    user = User(
        email=normalized_email,
        full_name=full_name,
        password_hash=hash_password(password),
        role=role,
    )
    db.add(user)
    db.flush()
    return user


def list_users(db: Session, page: int, page_size: int) -> list[User]:
    return UserRepository(db).list(page=page, page_size=page_size)


def get_user(db: Session, user_id: int) -> User:
    user = UserRepository(db).by_id(user_id)
    if user is None:
        raise DomainError("USER_NOT_FOUND", "User was not found.", 404)
    return user


def update_user(
    db: Session,
    target_id: int,
    actor: User,
    changes: dict,
) -> User:
    if not changes:
        raise DomainError("INVALID_USER_UPDATE", "Provide at least one user field to update.", 422)
    repository = UserRepository(db)
    record = repository.by_id(target_id)
    if record is None:
        raise DomainError("USER_NOT_FOUND", "User was not found.", 404)
    if "email" in changes:
        normalized_email = str(changes["email"]).lower()
        existing = repository.by_email(normalized_email)
        if existing is not None and existing.id != record.id:
            raise DomainError("DUPLICATE_USER", "An account with this email already exists.", 409)
        changes["email"] = normalized_email
    if "role" in changes and actor.role != Role.SUPER_ADMIN:
        raise DomainError("FORBIDDEN", "Only a super admin may assign roles.", 403)
    if record.role == Role.SUPER_ADMIN and record.id != actor.id and actor.role != Role.SUPER_ADMIN:
        raise DomainError("FORBIDDEN", "Only a super admin may modify another super admin.", 403)

    previous_role = record.role
    previous_active = record.is_active
    for field, value in changes.items():
        setattr(record, field, value)
    if previous_active and changes.get("is_active") is False:
        record.auth_token_version += 1
        RefreshTokenRepository(db).revoke_active_for_user(record.id, utcnow())

    if "role" in changes:
        action = "USER_ROLE_CHANGED"
    elif "is_active" in changes:
        action = "USER_DEACTIVATED" if changes["is_active"] is False else "USER_ACTIVATED"
    else:
        action = "USER_UPDATED"
    metadata = {key: str(value) for key, value in changes.items()}
    if "role" in changes:
        metadata["previous_role"] = previous_role.value
    if "is_active" in changes:
        metadata["previous_is_active"] = previous_active
    _audit(db, actor, action, "USER", record.id, metadata)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "email" in changes:
            raise DomainError(
                "DUPLICATE_USER",
                "An account with this email already exists.",
                409,
            ) from exc
        raise
    except Exception:
        db.rollback()
        raise
    return record
