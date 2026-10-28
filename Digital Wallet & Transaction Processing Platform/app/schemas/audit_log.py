from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogOut(BaseModel):
    id: int
    user_id: int | None
    action: str
    entity: str
    entity_id: int | None
    ip_address: str | None
    metadata_json: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


__all__ = ["AuditLogOut"]
