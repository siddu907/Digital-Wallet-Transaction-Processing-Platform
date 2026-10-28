from fastapi import APIRouter

from app.routers import (
    audit_logs,
    auth,
    dashboards,
    deposits,
    ledger,
    notifications,
    refunds,
    reports,
    suspicious_transactions,
    transaction_limits,
    transactions,
    transfers,
    users,
    wallets,
    withdrawals,
)

router = APIRouter()
for child_router in (
    auth.router,
    users.router,
    wallets.router,
    deposits.router,
    transfers.router,
    withdrawals.router,
    refunds.router,
    transactions.router,
    ledger.router,
    transaction_limits.router,
    suspicious_transactions.router,
    notifications.router,
    dashboards.router,
    audit_logs.router,
    reports.router,
):
    router.include_router(child_router)

__all__ = ["router"]
