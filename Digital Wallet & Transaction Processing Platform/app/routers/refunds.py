from fastapi import APIRouter
from typing import Annotated
from fastapi import Depends
from fastapi import Header
from fastapi import Query
from app.schemas import RefundCreate
from app.schemas import RefundOut
from app.models import Role
from sqlalchemy.orm import Session
from app.models import User
from app.services.refund_service import (
    create_refund as process_refund,
    decide_refund,
    mark_refund_under_review,
)
from app.dependencies import get_current_user
from app.database import get_db
from app.dependencies import require_roles
from app.routers._shared import _idempotency, admin_roles
from app.services.resource_query_service import get_refund as load_refund
from app.services.resource_query_service import list_refunds as load_refunds

router = APIRouter()

@router.post("/refunds", response_model=RefundOut, status_code=201)
def create_refund(payload: RefundCreate, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return process_refund(db, user, payload.ledger_entry_id, payload.amount, payload.reason, _idempotency(idempotency_key))


@router.get("/refunds", response_model=list[RefundOut])
def list_refunds(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_refunds(db, user, page, page_size)


@router.get("/refunds/{refund_id}", response_model=RefundOut)
def get_refund(refund_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_refund(db, refund_id, user)


@router.post("/refunds/{refund_id}/approve", response_model=RefundOut)
def approve_refund(refund_id: int, user: User = Depends(require_roles(*admin_roles, Role.SUPPORT_AGENT)), db: Session = Depends(get_db)):
    return decide_refund(db, refund_id, user, True)


@router.post("/refunds/{refund_id}/review", response_model=RefundOut)
def review_refund(refund_id: int, user: User = Depends(require_roles(*admin_roles, Role.SUPPORT_AGENT)), db: Session = Depends(get_db)):
    return mark_refund_under_review(db, refund_id, user)


@router.post("/refunds/{refund_id}/reject", response_model=RefundOut)
def reject_refund(refund_id: int, user: User = Depends(require_roles(*admin_roles, Role.SUPPORT_AGENT)), db: Session = Depends(get_db)):
    return decide_refund(db, refund_id, user, False)
