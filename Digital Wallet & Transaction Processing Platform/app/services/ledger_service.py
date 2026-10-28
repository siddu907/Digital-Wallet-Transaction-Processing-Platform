from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainError
from app.models import LedgerEntry, Role, User, Wallet
from app.repositories.ledger_repository import LedgerRepository


def wallet_history(db: Session, wallet: Wallet, *, page: int = 1, page_size: int = 20) -> list[LedgerEntry]:
    return LedgerRepository(db).for_wallet(wallet.id, page=page, page_size=page_size)


def list_ledger(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
) -> list[LedgerEntry]:
    owner_id = None if user.role in {Role.SUPER_ADMIN, Role.ADMIN, Role.SUPPORT_AGENT} else user.id
    return LedgerRepository(db).list(owner_id=owner_id, page=page, page_size=page_size)


def get_ledger_entry(db: Session, entry_id: int, user: User) -> LedgerEntry:
    row = LedgerRepository(db).get(entry_id)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Ledger entry was not found.", 404)
    from app.repositories.wallet_repository import WalletRepository

    wallet = WalletRepository(db).get(row.wallet_id)
    if wallet is not None and wallet.owner_id != user.id and user.role not in {
        Role.SUPER_ADMIN,
        Role.ADMIN,
        Role.SUPPORT_AGENT,
    }:
        raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
    return row


def get_wallet_history(
    db: Session,
    wallet_id: int,
    user: User,
) -> list[LedgerEntry]:
    from app.repositories.wallet_repository import WalletRepository

    wallet = WalletRepository(db).get(wallet_id)
    if wallet is None:
        raise DomainError("WALLET_NOT_FOUND", "Wallet was not found.", 404)
    if wallet.owner_id != user.id and user.role not in {
        Role.SUPER_ADMIN,
        Role.ADMIN,
        Role.SUPPORT_AGENT,
    }:
        raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
    return wallet_history(db, wallet)
