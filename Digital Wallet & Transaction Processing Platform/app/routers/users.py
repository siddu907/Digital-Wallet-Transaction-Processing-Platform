from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from app.core.exceptions import DomainError
from app.models import Role
from sqlalchemy.orm import Session
from app.models import User
from app.schemas import UserOut
from app.schemas import UserPatch
from app.schemas import UserRegister
from app.schemas import RoleChange
from app.services.auth_service import register as register_user
from app.database import get_db
from app.dependencies import require_roles
from app.routers._shared import admin_roles
from app.services.user_service import get_user as load_user
from app.services.user_service import list_users as load_users
from app.services.user_service import update_user

router = APIRouter()

@router.get("/users", response_model=list[UserOut], summary="List Users")
def list_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return load_users(db, page, page_size)


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserRegister, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return register_user(db, payload.email, payload.full_name, payload.password)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return load_user(db, user_id)


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(user_id: int, payload: UserPatch, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    return update_user(db, user_id, user, changes)


@router.patch("/users/{user_id}/activate", response_model=UserOut)
def activate_user(user_id: int, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return update_user(db, user_id, user, {"is_active": True})


@router.patch("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: int, user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return update_user(db, user_id, user, {"is_active": False})


@router.patch("/users/{user_id}/role", response_model=UserOut)
def change_user_role(user_id: int, payload: RoleChange, user: User = Depends(require_roles(Role.SUPER_ADMIN)), db: Session = Depends(get_db)):
    try:
        role = Role(payload.role.upper())
    except (ValueError, TypeError):
        raise DomainError("INVALID_ROLE", "Provide a valid role.", 422)
    return update_user(db, user_id, user, {"role": role})
