from fastapi import APIRouter
from typing import Annotated
from fastapi import Depends
from fastapi import Header
from fastapi import Query
from sqlalchemy.orm import Session
from app.models import Transfer
from app.schemas import TransferCreate
from app.schemas import TransferOut
from app.models import User
from app.services.transaction_service import cancel_operation
from app.services.transfer_service import create_transfer as process_transfer
from app.dependencies import get_current_user
from app.database import get_db
from app.routers._shared import _idempotency
from app.services.resource_query_service import get_transfer as load_transfer
from app.services.resource_query_service import list_transfers as load_transfers

router = APIRouter()

@router.post("/transfers", response_model=TransferOut, status_code=201)
def create_transfer(payload: TransferCreate, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return process_transfer(db, user, payload.sender_wallet_id, payload.receiver_wallet_id, payload.amount, _idempotency(idempotency_key))


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_transfers(db, user, page, page_size)


@router.get("/transfers/{transfer_id}", response_model=TransferOut)
def get_transfer(transfer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_transfer(db, transfer_id, user)


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return cancel_operation(db, Transfer, transfer_id, user)
