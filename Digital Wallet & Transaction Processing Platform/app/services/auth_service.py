from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import DomainError
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import AuditLog, RefreshToken, Role, User, utcnow
from app.services.audit_service import _audit
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository


def register(db: Session, email: str, full_name: str, password: str) -> User:
    email = email.lower()
    users = UserRepository(db)
    if users.by_email(email):
        raise DomainError("DUPLICATE_USER", "An account with this email already exists.", 409)
    user = User(email=email, full_name=full_name, password_hash=hash_password(password), role=Role.CUSTOMER)
    db.add(user)
    db.flush()
    _audit(db, user, "REGISTER", "USER", user.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DomainError("DUPLICATE_USER", "An account with this email already exists.", 409) from exc
    return user


def login(db: Session, email: str, password: str, ip: str | None) -> dict:
    user = UserRepository(db).by_email(email)
    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        db.add(AuditLog(user_id=user.id if user else None, action="LOGIN_FAILED", entity="USER", entity_id=user.id if user else None, ip_address=ip))
        db.commit()
        raise DomainError("INVALID_CREDENTIALS", "Email or password is incorrect.", 401)
    access, _, _ = create_token(
        user.id,
        "access",
        timedelta(minutes=settings.access_token_minutes),
        user.auth_token_version,
    )
    refresh, jti, expires = create_token(
        user.id,
        "refresh",
        timedelta(days=settings.refresh_token_days),
        user.auth_token_version,
    )
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires))
    db.add(AuditLog(user_id=user.id, action="LOGIN", entity="USER", entity_id=user.id, ip_address=ip))
    db.commit()
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


def refresh(db: Session, raw_token: str) -> dict:
    try:
        payload = decode_token(raw_token)
    except ValueError as exc:
        raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired.", 401) from exc
    if payload.get("type") != "refresh":
        raise DomainError("INVALID_REFRESH_TOKEN", "A refresh token is required.", 401)
    token_record = RefreshTokenRepository(db).by_jti(
        payload.get("jti"),
        lock=True,
    )
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token subject is invalid.", 401) from exc
    user = UserRepository(db).by_id(user_id)
    if (
        token_record is None
        or token_record.revoked_at is not None
        or user is None
        or not user.is_active
        or payload.get("ver", 0) != user.auth_token_version
    ):
        raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token has been revoked or is unavailable.", 401)
    token_record.revoked_at = utcnow()
    access, _, _ = create_token(
        user.id,
        "access",
        timedelta(minutes=settings.access_token_minutes),
        user.auth_token_version,
    )
    refresh_token, jti, expires = create_token(
        user.id,
        "refresh",
        timedelta(days=settings.refresh_token_days),
        user.auth_token_version,
    )
    db.add(RefreshToken(user_id=user.id, jti=jti, expires_at=expires))
    db.commit()
    return {"access_token": access, "refresh_token": refresh_token, "token_type": "bearer"}


def logout(db: Session, user: User, raw_token: str | None) -> None:
    if raw_token:
        try:
            payload = decode_token(raw_token)
        except ValueError as exc:
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token is invalid or expired.", 401) from exc
        if payload.get("type") != "refresh" or payload.get("sub") != str(user.id):
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token does not belong to this user.", 401)
        record = RefreshTokenRepository(db).for_user_jti(
            user.id,
            payload.get("jti"),
            lock=True,
        )
        if record is None:
            raise DomainError("INVALID_REFRESH_TOKEN", "Refresh token is unavailable.", 401)
    user = UserRepository(db).by_id_for_update(user.id)
    if user is None:
        raise DomainError("USER_NOT_FOUND", "User was not found.", 404)
    user.auth_token_version += 1
    RefreshTokenRepository(db).revoke_active_for_user(user.id, utcnow())
    _audit(db, user, "LOGOUT", "USER", user.id)
    db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> None:
    record = UserRepository(db).by_id_for_update(user.id)
    if record is None:
        raise DomainError("USER_NOT_FOUND", "User was not found.", 404)
    if not verify_password(current, record.password_hash):
        raise DomainError("INVALID_CREDENTIALS", "Current password is incorrect.", 400)
    record.password_hash = hash_password(new)
    record.auth_token_version += 1
    RefreshTokenRepository(db).revoke_active_for_user(record.id, utcnow())
    _audit(db, record, "CHANGE_PASSWORD", "USER", record.id)
    db.commit()


__all__ = ["register", "login", "refresh", "logout", "change_password"]
