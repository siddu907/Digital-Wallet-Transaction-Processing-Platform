from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, log_id: int) -> AuditLog | None:
        return self.session.get(AuditLog, log_id)

    def list(self, *, page: int = 1, page_size: int = 50) -> list[AuditLog]:
        query = select(AuditLog).order_by(AuditLog.created_at.desc())
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))
