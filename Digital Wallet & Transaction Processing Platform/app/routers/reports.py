from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import Role, User
from app.services.report_service import daily_transaction_report

router = APIRouter()


@router.get("/admin/reports/daily-transactions")
def daily_report(
    user: User = Depends(require_roles(Role.SUPER_ADMIN, Role.ADMIN)),
    db: Session = Depends(get_db),
):
    return daily_transaction_report(db)
