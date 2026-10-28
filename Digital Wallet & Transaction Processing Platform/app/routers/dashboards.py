from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import Role, User
from app.routers._shared import admin_roles, staff_roles
from app.services.dashboard_service import (
    admin_dashboard as build_admin_dashboard,
    customer_dashboard as build_customer_dashboard,
    support_dashboard as build_support_dashboard,
)

router = APIRouter()


@router.get("/dashboards/admin")
def admin_dashboard(user: User = Depends(require_roles(*admin_roles)), db: Session = Depends(get_db)):
    return build_admin_dashboard(db)


@router.get("/dashboards/support")
def support_dashboard(user: User = Depends(require_roles(*staff_roles)), db: Session = Depends(get_db)):
    return build_support_dashboard(db)


@router.get("/dashboards/customer")
def customer_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_customer_dashboard(db, user)
