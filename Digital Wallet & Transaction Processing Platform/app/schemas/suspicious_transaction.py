from app.models import RiskStatus
from pydantic import BaseModel


class SuspiciousReview(BaseModel):
    status: RiskStatus


__all__ = ["RiskStatus", "SuspiciousReview"]
