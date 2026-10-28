from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from app.schemas.suspicious_transaction import SuspiciousReview
from sqlalchemy.orm import Session
from app.models import User
from app.database import get_db
from app.dependencies import require_roles
from app.routers._shared import staff_roles
from app.services.risk_service import get_suspicious_transaction as load_suspicious_transaction
from app.services.risk_service import list_suspicious_transactions as load_suspicious_transactions
from app.services.risk_service import review_suspicious_transaction

router = APIRouter()

@router.get("/admin/suspicious-transactions")
def suspicious_transactions(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(require_roles(*staff_roles)), db: Session = Depends(get_db)):
    return load_suspicious_transactions(db, page, page_size)


@router.get("/admin/suspicious-transactions/{suspicious_id}")
def suspicious_detail(suspicious_id: int, user: User = Depends(require_roles(*staff_roles)), db: Session = Depends(get_db)):
    return load_suspicious_transaction(db, suspicious_id)


@router.post("/admin/suspicious-transactions/{suspicious_id}/review")
def review_suspicious(suspicious_id: int, payload: SuspiciousReview, user: User = Depends(require_roles(*staff_roles)), db: Session = Depends(get_db)):
    return review_suspicious_transaction(db, suspicious_id, user, payload.status)
