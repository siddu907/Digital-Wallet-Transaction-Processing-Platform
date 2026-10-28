from sqlalchemy import event, insert

from app.models.deposit import Deposit
from app.models.financial_identifier import FinancialIdentifier
from app.models.refund import Refund
from app.models.transaction_ledger import LedgerEntry
from app.models.transfer import Transfer
from app.models.withdrawal import Withdrawal


def _assign_financial_id(mapper, connection, target) -> None:
    if target.id is None:
        result = connection.execute(insert(FinancialIdentifier).values())
        target.id = result.inserted_primary_key[0]


for model in (Deposit, Transfer, Withdrawal, Refund, LedgerEntry):
    event.listen(model, "before_insert", _assign_financial_id)
