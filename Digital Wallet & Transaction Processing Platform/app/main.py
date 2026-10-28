from fastapi import FastAPI
from app.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.request_context import request_ip_middleware
from app.routers import audit_logs,auth,dashboards,deposits,ledger,notifications,refunds,reports,suspicious_transactions,transaction_limits,transactions,transfers,users,wallets,withdrawals


app = FastAPI(
    title="Digital Wallet Platform & Transaction Processing Platform",
    description="A wallet and transaction API with ledger-backed atomic operations.",
    version="1.0.0",
)
app.middleware("http")(request_ip_middleware)
app.include_router(auth.router, prefix="/api", tags=["Authentication"])
app.include_router(users.router, prefix="/api", tags=["Users"])
app.include_router(wallets.router, prefix="/api", tags=["Wallets"])
app.include_router(deposits.router, prefix="/api", tags=["Deposits"])
app.include_router(transfers.router, prefix="/api", tags=["Transfers"])
app.include_router(withdrawals.router, prefix="/api", tags=["Withdrawals"])
app.include_router(refunds.router, prefix="/api", tags=["Refunds"])
app.include_router(transactions.router, prefix="/api", tags=["Transactions"])
app.include_router(ledger.router, prefix="/api", tags=["Ledger"])
app.include_router(transaction_limits.router, prefix="/api", tags=["Transaction Limits"])
app.include_router(suspicious_transactions.router,prefix="/api",tags=["Suspicious Transactions"])
app.include_router(notifications.router, prefix="/api", tags=["Notifications"])
app.include_router(dashboards.router, prefix="/api", tags=["Dashboards"])
app.include_router(audit_logs.router, prefix="/api", tags=["Audit Logs"])
app.include_router(reports.router, prefix="/api", tags=["Reports"])
register_exception_handlers(app)
