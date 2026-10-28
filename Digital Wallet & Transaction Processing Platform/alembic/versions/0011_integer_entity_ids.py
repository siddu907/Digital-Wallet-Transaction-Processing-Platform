"""Reset the schema to use integer entity IDs.

This migration intentionally discards existing application data. Back up or
remove the database before applying it if any existing records must be kept.
"""

from alembic import op
import sqlalchemy as sa

from app.database import Base
from app import models


revision = "0011_integer_entity_ids"
down_revision = "0010_daily_limit_resets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS reject_transaction_ledger_mutation() CASCADE")
        op.execute("DROP FUNCTION IF EXISTS reject_audit_log_mutation() CASCADE")

    Base.metadata.drop_all(bind=bind)
    Base.metadata.create_all(bind=bind)

    op.execute(
        sa.text(
            "INSERT INTO roles (name, description) VALUES "
            "('SUPER_ADMIN', 'Full platform access'), "
            "('ADMIN', 'Administrative access'), "
            "('SUPPORT_AGENT', 'Customer support access'), "
            "('CUSTOMER', 'Wallet customer access')"
        )
    )

    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_transaction_ledger_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
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
        op.execute(
            """
            CREATE FUNCTION reject_audit_log_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit_logs is append-only'
                    USING ERRCODE = '55000';
            END;
            $$
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_logs_no_update_delete
            BEFORE UPDATE OR DELETE ON audit_logs
            FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation()
            """
        )
        op.execute(
            """
            CREATE TRIGGER audit_logs_no_truncate
            BEFORE TRUNCATE ON audit_logs
            FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_log_mutation()
            """
        )


def downgrade() -> None:
    raise RuntimeError(
        "Integer entity IDs cannot be downgraded because this migration discards prior data."
    )
