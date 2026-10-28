from sqlalchemy.orm import Session

from app.models import User
from app.repositories.dashboard_repository import DashboardRepository


def admin_dashboard(db: Session) -> dict:
    return DashboardRepository(db).admin()


def support_dashboard(db: Session) -> dict:
    return DashboardRepository(db).support()


def customer_dashboard(db: Session, user: User) -> dict:
    return DashboardRepository(db).customer(user)
