from app.core.exceptions import DomainError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models import User
from app.models import Wallet
from app.models import WalletStatus
from app.models import utcnow
from app.repositories.wallet_repository import WalletRepository
from app.services.financial_common import _wallet
from app.services.notification_service import _notify
from app.services.audit_service import _audit
from app.services.audit_service import _audit_failure


def create_wallet(db: Session, user: User, currency: str) -> Wallet:
    wallet = Wallet(owner_id=user.id, currency=currency)
    try:
        WalletRepository(db).add(wallet)
        _audit(db, user, "WALLET_CREATED", "WALLET", wallet.id, {"currency": wallet.currency})
        db.commit()
        return wallet
    except IntegrityError as exc:
        db.rollback()
        raise DomainError("DUPLICATE_WALLET", "A wallet already exists for this currency.", 409) from exc
    except Exception:
        db.rollback()
        raise


def set_wallet_status(db: Session, wallet_id: int, user: User, status: WalletStatus) -> Wallet:
    try:
        wallet = _wallet(db, wallet_id, lock=True)
        if user.role.value == "CUSTOMER" and wallet.owner_id != user.id:
            raise DomainError("FORBIDDEN", "You do not have access to this wallet.", 403)
        if status == WalletStatus.CLOSED and user.role.value not in {"SUPER_ADMIN", "ADMIN"}:
            raise DomainError("FORBIDDEN", "Only administrators may close wallets.", 403)
        if status == WalletStatus.SUSPENDED and user.role.value not in {"SUPER_ADMIN", "ADMIN"}:
            raise DomainError("FORBIDDEN", "Only administrators may suspend wallets.", 403)
        if user.role.value in {"CUSTOMER", "SUPPORT_AGENT"} and status not in {
            WalletStatus.ACTIVE,
            WalletStatus.FROZEN,
        }:
            raise DomainError("FORBIDDEN", "This role cannot set the requested wallet status.", 403)
        allowed = {
            WalletStatus.ACTIVE: {WalletStatus.FROZEN, WalletStatus.CLOSED, WalletStatus.SUSPENDED},
            WalletStatus.FROZEN: {WalletStatus.ACTIVE, WalletStatus.SUSPENDED},
            WalletStatus.SUSPENDED: {WalletStatus.ACTIVE, WalletStatus.CLOSED},
            WalletStatus.CLOSED: set(),
        }
        if status not in allowed[wallet.status]:
            raise DomainError("INVALID_WALLET_STATE", f"Cannot change wallet from {wallet.status.value} to {status.value}.", 409)
        if user.role.value == "CUSTOMER" and status == WalletStatus.ACTIVE and wallet.status != WalletStatus.FROZEN:
            raise DomainError("INVALID_WALLET_STATE", "Customers can only unfreeze a frozen wallet.", 409)
        previous_status = wallet.status
        if status == WalletStatus.FROZEN:
            wallet.last_frozen_at = utcnow()
        wallet.status = status
        event = "WALLET_FROZEN" if status == WalletStatus.FROZEN else "WALLET_UNFROZEN" if status == WalletStatus.ACTIVE else "WALLET_STATUS_CHANGED"
        _notify(db, wallet.owner_id, event, f"Wallet status changed to {status.value}.")
        _audit(db, user, event, "WALLET", wallet.id, {"from": previous_status.value, "to": status.value})
        db.commit()
        return wallet
    except DomainError as exc:
        db.rollback()
        _audit_failure(db, user, "TRANSACTION_BLOCKED", "WALLET", wallet_id, exc.code, {"requested_status": status.value})
        raise
