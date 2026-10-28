from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import WalletDailySummary
from app.repositories.wallet_daily_summary_repository import (
    WalletDailySummaryRepository,
)
from app.repositories.wallet_repository import WalletRepository


def create_daily_wallet_summary(db: Session, day: date | None = None) -> int:
    summary_day = day or datetime.now(timezone.utc).date()
    wallets = WalletRepository(db).all_for_update()
    summaries = WalletDailySummaryRepository(db)
    for wallet in wallets:
        summary = summaries.for_wallet_and_date(wallet.id, summary_day)
        if summary is None:
            summary = WalletDailySummary(wallet_id=wallet.id, summary_date=summary_day)
            db.add(summary)
        summary.available_balance = wallet.available_balance
        summary.pending_balance = wallet.pending_balance
    db.commit()
    return len(wallets)
