from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Notification


class NotificationRepository:
    def __init__(self, session: Session):
        self.session = session

    def for_user(self, user_id: int, *, unread_only: bool = False, page: int = 1, page_size: int = 20) -> list[Notification]:
        query = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            query = query.where(Notification.is_read.is_(False))
        query = query.order_by(Notification.created_at.desc())
        return list(self.session.scalars(query.offset((page - 1) * page_size).limit(page_size)))

    def get(self, notification_id: int) -> Notification | None:
        return self.session.get(Notification, notification_id)

    def mark_all_read(self, user_id: int) -> None:
        self.session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True)
        )
