from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import Deposit, Refund, Role, Transfer, User, Wallet, Withdrawal
from app.repositories.deposit_repository import DepositRepository
from app.repositories.refund_repository import RefundRepository
from app.repositories.transfer_repository import TransferRepository
from app.repositories.wallet_repository import WalletRepository
from app.repositories.withdrawal_repository import WithdrawalRepository


_STAFF_ROLES = {Role.SUPER_ADMIN, Role.ADMIN, Role.SUPPORT_AGENT}


def _staff(user: User) -> bool:
    return user.role in _STAFF_ROLES


def list_wallets(db: Session, user: User) -> list[Wallet]:
    return WalletRepository(db).list(owner_id=None if _staff(user) else user.id)


def get_wallet(db: Session, wallet_id: int, user: User) -> Wallet:
    wallet = WalletRepository(db).get(wallet_id)
    if wallet is None:
        raise DomainError("WALLET_NOT_FOUND", "Wallet was not found.", 404)
    if wallet.owner_id != user.id and not _staff(user):
        raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
    return wallet


def list_deposits(db: Session, user: User, page: int, page_size: int) -> list[Deposit]:
    return DepositRepository(db).list(
        user_id=None if _staff(user) else user.id,
        page=page,
        page_size=page_size,
    )


def get_deposit(db: Session, deposit_id: int, user: User) -> Deposit:
    row = DepositRepository(db).get(deposit_id)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Deposit was not found.", 404)
    if row.user_id != user.id and not _staff(user):
        raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
    return row


def list_transfers(db: Session, user: User, page: int, page_size: int) -> list[Transfer]:
    return TransferRepository(db).list(
        user_id=None if _staff(user) else user.id,
        page=page,
        page_size=page_size,
    )


def get_transfer(db: Session, transfer_id: int, user: User) -> Transfer:
    row = TransferRepository(db).get(transfer_id)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Transfer was not found.", 404)
    receiver_wallet = WalletRepository(db).get(row.receiver_wallet_id)
    owns_transfer = (
        row.user_id == user.id
        or (receiver_wallet is not None and receiver_wallet.owner_id == user.id)
    )
    if not owns_transfer and not _staff(user):
        raise DomainError("FORBIDDEN", "You do not have access to this transfer.", 403)
    return row


def list_withdrawals(db: Session, user: User, page: int, page_size: int) -> list[Withdrawal]:
    return WithdrawalRepository(db).list(
        user_id=None if _staff(user) else user.id,
        page=page,
        page_size=page_size,
    )


def get_withdrawal(db: Session, withdrawal_id: int, user: User) -> Withdrawal:
    row = WithdrawalRepository(db).get(withdrawal_id)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Withdrawal was not found.", 404)
    if row.user_id != user.id and not _staff(user):
        raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
    return row


def list_refunds(db: Session, user: User, page: int, page_size: int) -> list[Refund]:
    return RefundRepository(db).list(
        user_id=None if _staff(user) else user.id,
        page=page,
        page_size=page_size,
    )


def get_refund(db: Session, refund_id: int, user: User) -> Refund:
    row = RefundRepository(db).get(refund_id)
    if row is None:
        raise DomainError("INVALID_REFUND", "Refund was not found.", 404)
    if row.user_id != user.id and not _staff(user):
        raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
    return row
