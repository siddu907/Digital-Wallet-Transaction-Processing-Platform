from fastapi import APIRouter
from fastapi import Depends
from app.schemas import PasswordChange
from app.schemas import RefreshRequest
from fastapi import Request
from sqlalchemy.orm import Session
from app.schemas import TokenPair
from app.models import User
from app.schemas import UserLogin
from app.schemas import UserOut
from app.schemas import UserRegister
from app.services.auth_service import change_password as change_user_password
from app.services.auth_service import login as login_user
from app.services.auth_service import logout as logout_user
from app.services.auth_service import refresh as refresh_tokens
from app.services.auth_service import register as register_user
from app.dependencies import get_current_user
from app.database import get_db

router = APIRouter()

@router.post("/auth/register", response_model=UserOut, status_code=201)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    return register_user(db, payload.email, payload.full_name, payload.password)


@router.post("/auth/login", response_model=TokenPair)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    return login_user(db, payload.email, payload.password, request.client.host if request.client else None)


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    return refresh_tokens(db, payload.refresh_token)


@router.post("/auth/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logout_user(db, user, None)
    return {"success": True, "message": "Logged out."}


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/change-password")
def change_password(payload: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    change_user_password(db, user, payload.current_password, payload.new_password)
    return {"success": True, "message": "Password changed"}
