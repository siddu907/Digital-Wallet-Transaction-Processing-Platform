from fastapi import APIRouter
from app.schemas import AmountRequest
from typing import Annotated
from fastapi import Depends
from fastapi import Header
from fastapi import Query
from sqlalchemy.orm import Session
from app.models import Deposit
from app.models import User
from app.services.deposit_service import create_deposit as process_deposit
from app.services.transaction_service import cancel_operation
from app.dependencies import get_current_user
from app.database import get_db
from app.routers._shared import _idempotency
from app.services.resource_query_service import get_deposit as load_deposit
from app.services.resource_query_service import list_deposits as load_deposits

router = APIRouter()

@router.post("/wallets/{wallet_id}/deposits", status_code=201)
def create_deposit(wallet_id: int, payload: AmountRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return process_deposit(db, user, wallet_id, payload.amount, _idempotency(idempotency_key))


@router.get("/deposits")
def list_deposits(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_deposits(db, user, page, page_size)


@router.get("/deposits/{deposit_id}")
def get_deposit(deposit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_deposit(db, deposit_id, user)


@router.post("/deposits/{deposit_id}/cancel")
def cancel_deposit(deposit_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return cancel_operation(db, Deposit, deposit_id, user)
