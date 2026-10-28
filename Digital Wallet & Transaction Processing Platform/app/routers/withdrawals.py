from fastapi import APIRouter
from app.schemas import AmountRequest
from typing import Annotated
from fastapi import Depends
from fastapi import Header
from fastapi import Query
from sqlalchemy.orm import Session
from app.models import Withdrawal
from app.models import User
from app.services.transaction_service import cancel_operation
from app.services.withdrawal_service import create_withdrawal as process_withdrawal
from app.dependencies import get_current_user
from app.database import get_db
from app.routers._shared import _idempotency
from app.services.resource_query_service import get_withdrawal as load_withdrawal
from app.services.resource_query_service import list_withdrawals as load_withdrawals

router = APIRouter()

@router.post("/wallets/{wallet_id}/withdrawals", status_code=201)
def create_withdrawal(wallet_id: int, payload: AmountRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return process_withdrawal(db, user, wallet_id, payload.amount, _idempotency(idempotency_key))


@router.get("/withdrawals")
def list_withdrawals(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_withdrawals(db, user, page, page_size)


@router.get("/withdrawals/{withdrawal_id}")
def get_withdrawal(withdrawal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_withdrawal(db, withdrawal_id, user)


@router.post("/withdrawals/{withdrawal_id}/cancel")
def cancel_withdrawal(withdrawal_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return cancel_operation(db, Withdrawal, withdrawal_id, user)
