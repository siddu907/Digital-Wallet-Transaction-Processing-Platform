from decimal import Decimal

from pydantic import BaseModel


class AdminDashboard(BaseModel):
    total_users: int
    active_wallets: int
    total_wallet_balance: Decimal
    wallet_balances_by_currency: dict[str, Decimal]
    today_transactions: int
    today_transaction_volume: Decimal
    failed_transactions: int
    suspicious_transactions: int


class SupportDashboard(BaseModel):
    pending_reviews: int
    suspicious_transactions: int
    failed_transactions: int
    refund_requests: int
    frozen_wallets: int


class CustomerDashboard(BaseModel):
    wallets: list[dict]
    wallet_balance: dict[str, dict[str, Decimal]]
    recent_transactions: list[dict]
    total_deposits: Decimal
    total_transfers: Decimal
    total_withdrawals: Decimal
    pending_transactions: int
