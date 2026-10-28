from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from app.models import User
from app.database import get_db
from app.dependencies import require_roles
from app.routers._shared import admin_roles
from app.services.audit_service import get_audit_log as load_audit_log
from app.services.audit_service import list_audit_logs as load_audit_logs

router = APIRouter()

@router.get("/admin/audit-logs")
def list_audit_logs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return load_audit_logs(db, page, page_size)


@router.get("/admin/audit-logs/{log_id}")
def get_audit_log(log_id: int, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return load_audit_log(db, log_id)
