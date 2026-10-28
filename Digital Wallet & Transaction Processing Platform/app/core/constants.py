from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    SUPPORT_AGENT = "SUPPORT_AGENT"
    CUSTOMER = "CUSTOMER"


class WalletStatus(str, Enum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


class OperationStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class LedgerType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER_DEBIT = "TRANSFER_DEBIT"
    TRANSFER_CREDIT = "TRANSFER_CREDIT"
    REFUND = "REFUND"
    FEE = "FEE"
    ADJUSTMENT = "ADJUSTMENT"
    REVERSAL = "REVERSAL"


class RefundStatus(str, Enum):
    REQUESTED = "REQUESTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RiskStatus(str, Enum):
    NORMAL = "NORMAL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
