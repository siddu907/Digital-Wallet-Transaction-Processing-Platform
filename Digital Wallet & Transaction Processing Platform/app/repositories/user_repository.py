from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def by_email(self, email: str) -> User | None:
        return self.session.scalar(select(User).where(User.email == email.lower()))

    def by_email_for_update(self, email: str) -> User | None:
        return self.session.scalar(
            select(User).where(User.email == email.lower()).with_for_update()
        )

    def by_id_for_update(self, user_id: int) -> User | None:
        return self.session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )

    def list(self, *, page: int = 1, page_size: int = 20) -> list[User]:
        query = select(User).order_by(User.created_at.desc())
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))
