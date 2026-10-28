from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.daily_limit_reset_repository import DailyLimitResetRepository


def _utc_iso(value) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def reset_daily_limits(db: Session) -> dict:
    reset_date = datetime.now(timezone.utc).date()
    repository = DailyLimitResetRepository(db)
    existing = repository.get(reset_date)
    if existing is not None:
        return {
            "reset_date": reset_date.isoformat(),
            "reset_at": _utc_iso(existing.completed_at),
            "strategy": existing.strategy,
            "already_reset": True,
        }
    try:
        record = repository.add(reset_date)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = repository.get(reset_date)
        if existing is None:
            raise
        return {
            "reset_date": reset_date.isoformat(),
            "reset_at": _utc_iso(existing.completed_at),
            "strategy": existing.strategy,
            "already_reset": True,
        }
    except Exception:
        db.rollback()
        raise
    return {
        "reset_date": reset_date.isoformat(),
        "reset_at": _utc_iso(record.completed_at),
        "strategy": record.strategy,
        "already_reset": False,
    }


run = reset_daily_limits
