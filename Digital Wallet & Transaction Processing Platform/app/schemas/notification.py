from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: int
    user_id: int
    event: str
    message: str
    is_read: bool
    created_at: datetime


__all__ = ["NotificationOut"]
