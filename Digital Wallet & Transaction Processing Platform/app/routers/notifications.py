from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from app.models import User
from app.dependencies import get_current_user
from app.database import get_db
from app.services.notification_service import list_notifications as load_notifications
from app.services.notification_service import mark_all_notifications_read
from app.services.notification_service import mark_notification_read

router = APIRouter()

@router.get("/notifications")
def list_notifications(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_notifications(db, user, page=page, page_size=page_size)


@router.patch("/notifications/read-all")
def read_all_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mark_all_notifications_read(db, user)
    return {"success": True}


@router.patch("/notifications/{notification_id}/read")
def read_notification(notification_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return mark_notification_read(db, notification_id, user)
