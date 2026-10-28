from app.models import Notification
from app.core.exceptions import DomainError
from app.models import User
from app.repositories.notification_repository import NotificationRepository
from sqlalchemy.orm import Session


def _notify(db: Session, user_id: int, event: str, message: str) -> None:
    db.add(Notification(user_id=user_id, event=event, message=message))


def list_notifications(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
) -> list[Notification]:
    return NotificationRepository(db).for_user(
        user.id,
        page=page,
        page_size=page_size,
    )


def mark_notification_read(
    db: Session,
    notification_id: int,
    user: User,
) -> Notification:
    repository = NotificationRepository(db)
    row = repository.get(notification_id)
    if row is None:
        raise DomainError("NOTIFICATION_NOT_FOUND", "Notification was not found.", 404)
    if row.user_id != user.id:
        raise DomainError("FORBIDDEN", "You do not own this notification.", 403)
    row.is_read = True
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return row


def mark_all_notifications_read(db: Session, user: User) -> None:
    NotificationRepository(db).mark_all_read(user.id)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
