from sqlalchemy.orm import Session

from app.services.refund_service import complete_approved_refunds


def process_approved_refunds(db: Session) -> int:
    return complete_approved_refunds(db)


run = process_approved_refunds
