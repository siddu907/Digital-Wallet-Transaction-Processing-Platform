from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RoleRecord


class RoleRepository:
    def __init__(self, session: Session):
        self.session = session

    def all(self) -> list[RoleRecord]:
        return list(self.session.scalars(select(RoleRecord).order_by(RoleRecord.name)))
