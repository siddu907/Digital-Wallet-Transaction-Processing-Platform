from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from sqlalchemy.orm import Session
from app.models import User
from app.dependencies import get_current_user
from app.database import get_db
from app.services.ledger_service import get_ledger_entry, get_wallet_history
from app.services.ledger_service import list_ledger as load_ledger

router = APIRouter()

@router.get("/ledger")
def list_ledger(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_ledger(db, user, page=page, page_size=page_size)


@router.get("/ledger/{ledger_id}")
def get_ledger(ledger_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_ledger_entry(db, ledger_id, user)


@router.get("/wallets/{wallet_id}/ledger")
def wallet_ledger(wallet_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_wallet_history(db, wallet_id, user)
