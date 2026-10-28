from app.core.exceptions import DomainError
from app.models import LedgerType, OperationStatus, Transfer, Withdrawal
from sqlalchemy.orm import Session
from app.models import Deposit, LedgerEntry, Refund, RefundStatus, Role, User, Wallet
from datetime import date
from app.repositories.transaction_repository import TransactionRepository
from app.services.audit_service import _audit
from app.services.financial_common import _ledger
from app.services.notification_service import _notify
from app.services.audit_service import _audit_failure


def cancel_operation(db: Session, model, operation_id: int, user: User):
    repository = TransactionRepository(db)
    row = repository.get_operation(model, operation_id, lock=True)
    if row is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Transaction was not found.", 404)
    if row.user_id != user.id:
        raise DomainError("FORBIDDEN", "You do not own this transaction.", 403)
    if row.status == OperationStatus.CANCELLED:
        _audit_failure(
            db,
            user,
            "TRANSACTION_BLOCKED",
            model.__tablename__.upper(),
            operation_id,
            "INVALID_TRANSACTION_STATE",
        )
        raise DomainError("INVALID_TRANSACTION_STATE", "Transaction has already been cancelled.", 409)

    if model is Withdrawal and row.status == OperationStatus.COMPLETED:
        wallet = repository.get_wallet(row.wallet_id, lock=True)
        if wallet is None:
            raise DomainError("WALLET_NOT_FOUND", "Withdrawal wallet was not found.", 404)
        before = wallet.available_balance
        wallet.available_balance += row.amount
        _ledger(
            db,
            wallet,
            LedgerType.REVERSAL,
            row.amount,
            before,
            "WITHDRAWAL",
            row.id,
            user,
            "Withdrawal cancellation reversal",
        )
        row.status = OperationStatus.CANCELLED
        _notify(
            db,
            row.user_id,
            "WITHDRAWAL_CANCELLED",
            f"Withdrawal {row.reference} was cancelled and reversed.",
        )
        _audit(db, user, "WITHDRAWAL_CANCELLED", "WITHDRAWAL", row.id, {"amount": str(row.amount), "currency": row.currency})
        db.commit()
        return row

    if row.status not in {OperationStatus.PENDING, OperationStatus.PROCESSING}:
        _audit_failure(
            db,
            user,
            "TRANSACTION_BLOCKED",
            model.__tablename__.upper(),
            operation_id,
            "INVALID_TRANSACTION_STATE",
        )
        raise DomainError(
            "INVALID_TRANSACTION_STATE",
            "Only pending or processing transactions can be cancelled.",
            409,
        )
    row.status = OperationStatus.CANCELLED
    if model is Transfer:
        _audit(db, user, "TRANSFER_CANCELLED", "TRANSFER", row.id)
        receiver = repository.get_wallet(row.receiver_wallet_id)
        if receiver is not None:
            _notify(
                db,
                receiver.owner_id,
                "TRANSFER_CANCELLED",
                f"Transfer {row.reference} was cancelled.",
            )
    db.commit()
    return row


def transaction_history(
    db: Session,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    transaction_type: str | None = None,
    status: str | None = None,
    minimum_amount=None,
    maximum_amount=None,
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    if minimum_amount is not None and maximum_amount is not None and minimum_amount > maximum_amount:
        raise DomainError("INVALID_TRANSACTION_FILTER", "min_amount cannot exceed max_amount.", 422)
    if from_date is not None and to_date is not None and from_date > to_date:
        raise DomainError("INVALID_TRANSACTION_FILTER", "from_date cannot be after to_date.", 422)
    sort_columns = {"created_at", "amount"}
    if sort_by not in sort_columns or sort_order not in {"asc", "desc"}:
        raise DomainError("INVALID_TRANSACTION_SORT", "Unsupported transaction sort option.", 422)
    transaction_kinds = None
    if transaction_type:
        normalized_type = transaction_type.upper()
        transaction_kinds = {
            "TRANSFER": ["TRANSFER_DEBIT", "TRANSFER_CREDIT"],
            "DEPOSIT": ["DEPOSIT"],
            "WITHDRAWAL": ["WITHDRAWAL"],
            "REFUND": ["REFUND"],
        }.get(normalized_type)
        if transaction_kinds is None:
            if normalized_type not in LedgerType.__members__:
                raise DomainError("INVALID_TRANSACTION_TYPE", "Unsupported transaction type filter.", 422)
            transaction_kinds = [normalized_type]
    normalized_status = None
    if status:
        normalized_status = status.upper()
        if (
            normalized_status not in OperationStatus.__members__
            and normalized_status not in RefundStatus.__members__
        ):
            raise DomainError("INVALID_TRANSACTION_STATUS", "Unsupported transaction status filter.", 422)
    staff_roles = {Role.SUPER_ADMIN, Role.ADMIN, Role.SUPPORT_AGENT}
    return TransactionRepository(db).transaction_history(
        user_id=None if user.role in staff_roles else user.id,
        page=page,
        page_size=page_size,
        transaction_kinds=transaction_kinds,
        status=normalized_status,
        minimum_amount=minimum_amount,
        maximum_amount=maximum_amount,
        from_date=from_date,
        to_date=to_date,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


def get_transaction(db: Session, transaction_id: int, user: User):
    repository = TransactionRepository(db)
    row = repository.get_ledger_entry(transaction_id)
    staff_roles = {Role.SUPER_ADMIN, Role.ADMIN, Role.SUPPORT_AGENT}
    if row is not None:
        wallet = repository.get_wallet(row.wallet_id)
        if (
            wallet is not None
            and wallet.owner_id != user.id
            and user.role not in staff_roles
        ):
            raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
        operation = repository.by_reference(row.reference_entity, row.reference_id)
        return {
            "id": row.id,
            "wallet_id": row.wallet_id,
            "transaction_type": row.transaction_type,
            "amount": row.amount,
            "balance_before": row.balance_before,
            "balance_after": row.balance_after,
            "status": operation.status if operation is not None else None,
            "reference_entity": row.reference_entity,
            "reference_id": row.reference_id,
            "description": row.description,
            "created_by": row.created_by,
            "metadata_json": row.metadata_json,
            "created_at": row.created_at,
        }

    operation = repository.get_unposted_operation(transaction_id)
    if operation is None:
        raise DomainError("TRANSACTION_NOT_FOUND", "Transaction was not found.", 404)

    if isinstance(operation, Transfer):
        sender_wallet = repository.get_wallet(operation.sender_wallet_id)
        receiver_wallet = repository.get_wallet(operation.receiver_wallet_id)
        if user.role not in staff_roles and user.id not in {
            operation.user_id,
            receiver_wallet.owner_id if receiver_wallet is not None else None,
        }:
            raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
        is_receiver = (
            user.role not in staff_roles
            and receiver_wallet is not None
            and receiver_wallet.owner_id == user.id
            and operation.user_id != user.id
        )
        wallet_id = operation.receiver_wallet_id if is_receiver else operation.sender_wallet_id
        transaction_type = LedgerType.TRANSFER_CREDIT if is_receiver else LedgerType.TRANSFER_DEBIT
        description = "Incoming transfer" if is_receiver else "Outgoing transfer"
    else:
        if operation.user_id != user.id and user.role not in staff_roles:
            raise DomainError("FORBIDDEN", "You do not have access to this resource.", 403)
        wallet_id = operation.wallet_id
        if isinstance(operation, Deposit):
            transaction_type = LedgerType.DEPOSIT
            description = "Deposit operation"
        elif isinstance(operation, Withdrawal):
            transaction_type = LedgerType.WITHDRAWAL
            description = "Withdrawal operation"
        else:
            transaction_type = LedgerType.REFUND
            description = operation.reason

    entity = operation.__tablename__.rstrip("s").upper()
    return {
        "id": operation.id,
        "wallet_id": wallet_id,
        "transaction_type": transaction_type,
        "amount": operation.amount,
        "balance_before": None,
        "balance_after": None,
        "status": operation.status,
        "reference_entity": entity,
        "reference_id": operation.id,
        "description": description,
        "created_by": operation.user_id,
        "metadata_json": {},
        "created_at": operation.created_at,
    }
