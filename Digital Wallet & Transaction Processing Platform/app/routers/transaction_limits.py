from fastapi import APIRouter
from fastapi import Depends
from app.schemas import LimitsPatch
from sqlalchemy.orm import Session
from app.models import User
from app.services.transaction_limit_service import get_limits as load_transaction_limits
from app.services.transaction_limit_service import update_limits
from app.database import get_db
from app.dependencies import require_roles
from app.routers._shared import admin_roles

router = APIRouter()

@router.get("/admin/transaction-limits")
def get_limits(user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return load_transaction_limits(db)


@router.patch("/admin/transaction-limits")
def patch_limits(payload: LimitsPatch, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return update_limits(db, user, payload.model_dump(mode="json", exclude_unset=True))
