from sqlalchemy.orm import Session

from app.services.risk_service import scan_suspicious_transactions as scan


def scan_suspicious_transactions(db: Session) -> int:
    return scan(db)


run = scan_suspicious_transactions
