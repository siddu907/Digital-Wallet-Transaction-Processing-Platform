from fastapi import APIRouter
from decimal import Decimal
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from app.models import User
from app.schemas.transaction import TransactionHistoryOut, TransactionOut
from datetime import date
from app.dependencies import get_current_user
from app.database import get_db
from app.services.transaction_service import get_transaction as load_transaction
from app.services.transaction_service import transaction_history as load_transaction_history

router = APIRouter()

@router.get("/transactions", response_model=TransactionHistoryOut)
def transaction_history(
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    type: str | None = None, status: str | None = None, min_amount: Decimal | None = Query(None, ge=0),
    max_amount: Decimal | None = Query(None, ge=0), from_date: date | None = None,
    to_date: date | None = None, search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|amount)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    return load_transaction_history(
        db,
        user,
        page=page,
        page_size=page_size,
        transaction_type=type,
        status=status,
        minimum_amount=min_amount,
        maximum_amount=max_amount,
        from_date=from_date,
        to_date=to_date,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_transaction(db, transaction_id, user)
