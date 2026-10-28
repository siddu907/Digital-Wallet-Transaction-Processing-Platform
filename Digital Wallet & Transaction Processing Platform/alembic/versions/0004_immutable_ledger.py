"""Prevent updates and deletes to posted ledger entries."""

from alembic import op


revision = "0004_immutable_ledger"
down_revision = "0003_user_auth_token_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE FUNCTION reject_transaction_ledger_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'transaction_ledger is append-only'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER transaction_ledger_no_update_delete
        BEFORE UPDATE OR DELETE ON transaction_ledger
        FOR EACH ROW EXECUTE FUNCTION reject_transaction_ledger_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER transaction_ledger_no_truncate
        BEFORE TRUNCATE ON transaction_ledger
        FOR EACH STATEMENT EXECUTE FUNCTION reject_transaction_ledger_mutation()
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER transaction_ledger_no_truncate ON transaction_ledger")
    op.execute("DROP TRIGGER transaction_ledger_no_update_delete ON transaction_ledger")
    op.execute("DROP FUNCTION reject_transaction_ledger_mutation()")
