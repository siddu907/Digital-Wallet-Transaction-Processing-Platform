from datetime import datetime, timedelta, timezone
import uuid

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

password_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    pbkdf2_sha256__rounds=600_000,
    deprecated="auto",
)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


def create_token(
    subject: int | str,
    token_type: str,
    expires_delta: timedelta,
    token_version: int = 0,
) -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + expires_delta
    jti = str(uuid.uuid4())
    token = jwt.encode(
        {
            "sub": str(subject),
            "type": token_type,
            "jti": jti,
            "ver": token_version,
            "iat": now,
            "exp": expires,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, expires


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
