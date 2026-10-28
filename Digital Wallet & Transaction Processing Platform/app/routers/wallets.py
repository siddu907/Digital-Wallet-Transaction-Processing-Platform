from fastapi import APIRouter
from fastapi import Depends
from app.core.exceptions import DomainError
from app.models import Role
from sqlalchemy.orm import Session
from app.models import User
from app.models import Wallet
from app.schemas import WalletCreate
from app.schemas import WalletOut
from app.schemas import WalletPatch
from app.models import WalletStatus
from app.services.wallet_service import create_wallet as create_customer_wallet
from app.services.wallet_service import set_wallet_status
from app.dependencies import get_current_user
from app.database import get_db
from app.dependencies import require_roles
from app.routers._shared import admin_roles
from app.services.resource_query_service import get_wallet as load_wallet
from app.services.resource_query_service import list_wallets as load_wallets

router = APIRouter()

@router.post("/wallets", response_model=WalletOut, status_code=201)
def create_wallet(payload: WalletCreate, user: User = Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)):
    return create_customer_wallet(db, user, payload.currency)


@router.get("/wallets", response_model=list[WalletOut])
def list_wallets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_wallets(db, user)


@router.get("/wallets/{wallet_id}", response_model=WalletOut)
def get_wallet(wallet_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_wallet(db, wallet_id, user)


@router.patch("/wallets/{wallet_id}", response_model=WalletOut)
def patch_wallet(wallet_id: int, payload: WalletPatch, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    load_wallet(db, wallet_id, user)
    if payload.status is None:
        raise DomainError("INVALID_WALLET_STATE", "No supported wallet fields were provided.", 400)
    wallet = set_wallet_status(db, wallet_id, user, payload.status)
    return wallet


@router.post("/wallets/{wallet_id}/freeze", response_model=WalletOut)
def freeze_wallet(wallet_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return set_wallet_status(db, wallet_id, user, WalletStatus.FROZEN)


@router.post("/wallets/{wallet_id}/unfreeze", response_model=WalletOut)
def unfreeze_wallet(wallet_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return set_wallet_status(db, wallet_id, user, WalletStatus.ACTIVE)


@router.post("/wallets/{wallet_id}/close", response_model=WalletOut)
def close_wallet(wallet_id: int, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return set_wallet_status(db, wallet_id, user, WalletStatus.CLOSED)
