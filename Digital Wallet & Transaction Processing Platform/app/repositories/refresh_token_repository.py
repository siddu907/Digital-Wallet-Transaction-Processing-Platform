from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: Session):
        self.session = session

    def by_jti(self, jti: str, *, lock: bool = False) -> RefreshToken | None:
        query = select(RefreshToken).where(RefreshToken.jti == jti)
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def for_user_jti(
        self,
        user_id: int,
        jti: str,
        *,
        lock: bool = False,
    ) -> RefreshToken | None:
        query = select(RefreshToken).where(
            RefreshToken.jti == jti,
            RefreshToken.user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        return self.session.scalar(query)

    def revoke_active_for_user(self, user_id: int, revoked_at) -> None:
        self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=revoked_at)
        )
