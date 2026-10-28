from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WalletDailySummary


class WalletDailySummaryRepository:
    def __init__(self, session: Session):
        self.session = session

    def for_wallet_and_date(
        self,
        wallet_id: int,
        summary_date: date,
    ) -> WalletDailySummary | None:
        return self.session.scalar(
            select(WalletDailySummary).where(
                WalletDailySummary.wallet_id == wallet_id,
                WalletDailySummary.summary_date == summary_date,
            )
        )
