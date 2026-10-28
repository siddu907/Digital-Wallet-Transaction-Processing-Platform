from decimal import Decimal

from app.models import AuditLog, RiskStatus, SuspiciousTransaction
from sqlalchemy.orm import Session
from app.models import User, utcnow
from app.core.request_context import current_request_ip
from app.core.exceptions import DomainError
from app.repositories.audit_log_repository import AuditLogRepository
from app.services.notification_service import _notify


def _audit(db: Session, user: User, action: str, entity: str, entity_id: int, metadata: dict | None = None) -> None:
    db.add(
        AuditLog(
            user_id=user.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            ip_address=current_request_ip(),
            metadata_json=metadata or {},
        )
    )


def _audit_failure(
    db: Session,
    user: User,
    action: str,
    entity: str,
    entity_id: int | None,
    error_code: str,
    metadata: dict | None = None,
) -> None:
    details = dict(metadata or {})
    details["error_code"] = error_code
    db.add(
        AuditLog(
            user_id=user.id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            ip_address=current_request_ip(),
            metadata_json=details,
        )
    )
    db.commit()


def _audit_system_event(
    db: Session,
    action: str,
    entity: str,
    entity_id: int | None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            ip_address=current_request_ip(),
            metadata_json=metadata or {},
            created_at=utcnow(),
        )
    )


def _flag_limit_attempt(
    db: Session,
    user: User,
    operation: str,
    wallet_id: int,
    amount: Decimal,
    error_code: str,
) -> None:
    db.add(
        SuspiciousTransaction(
            user_id=user.id,
            wallet_id=wallet_id,
            operation_type=operation,
            operation_id=None,
            amount=amount,
            status=RiskStatus.REVIEW_REQUIRED,
            reason=f"Rejected operation exceeded a configured limit ({error_code}).",
        )
    )
    failure_event = {
        "DEPOSIT": "DEPOSIT_FAILED",
        "TRANSFER": "TRANSFER_FAILED",
        "WITHDRAWAL": "WITHDRAWAL_FAILED",
        "REFUND": "REFUND_FAILED",
    }.get(operation)
    if failure_event is not None:
        _notify(
            db,
            user.id,
            failure_event,
            f"Your {operation.lower()} attempt was rejected because it exceeded a transaction limit.",
        )
    _notify(
        db,
        user.id,
        "SUSPICIOUS_TRANSACTION",
        f"A {operation.lower()} attempt was blocked by a configured transaction limit and flagged for review.",
    )
    _audit_failure(
        db,
        user,
        "TRANSACTION_BLOCKED",
        operation,
        wallet_id,
        error_code,
        {"amount": str(amount), "risk_status": RiskStatus.REVIEW_REQUIRED.value},
    )


def list_audit_logs(db: Session, page: int, page_size: int) -> list[AuditLog]:
    return AuditLogRepository(db).list(page=page, page_size=page_size)


def get_audit_log(db: Session, log_id: int) -> AuditLog:
    row = AuditLogRepository(db).get(log_id)
    if row is None:
        raise DomainError("AUDIT_LOG_NOT_FOUND", "Audit log was not found.", 404)
    return row
