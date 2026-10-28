from app.models import Deposit
from app.core.exceptions import DomainError
from app.repositories import FinanceRepository
from app.models import IdempotencyKey
from app.models import Refund
from sqlalchemy.orm import Session
from app.models import Transfer
from app.models import Withdrawal
import hashlib
import json


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _replay(db: Session, user_id: int, key: str, digest: str, entity: str):
    saved = FinanceRepository(db).get_idempotency_key(user_id, key)
    if saved is None:
        return None
    if saved.request_hash != digest or saved.entity_type != entity:
        raise DomainError("DUPLICATE_IDEMPOTENCY_KEY", "This idempotency key was already used for a different request.", 409)
    model = {"DEPOSIT": Deposit, "TRANSFER": Transfer, "WITHDRAWAL": Withdrawal, "REFUND": Refund}[entity]
    return FinanceRepository(db).get_entity(model, saved.entity_id)


def _record_idempotency(db: Session, user_id: int, key: str, digest: str, entity: str, entity_id: int) -> None:
    db.add(IdempotencyKey(user_id=user_id, key=key, request_hash=digest, entity_type=entity, entity_id=entity_id))
