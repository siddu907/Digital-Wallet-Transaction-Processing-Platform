"""Represent suspicious transaction attempts without a posted transfer."""

from alembic import op
import sqlalchemy as sa


revision = "0007_generic_risk_events"
down_revision = "0006_audit_actor_restrict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suspicious_transactions",
        sa.Column("user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "suspicious_transactions",
        sa.Column("wallet_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "suspicious_transactions",
        sa.Column("operation_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "suspicious_transactions",
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
    )
    op.alter_column(
        "suspicious_transactions",
        "transfer_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.create_foreign_key(
        "fk_suspicious_transactions_user_id_users",
        "suspicious_transactions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_suspicious_transactions_wallet_id_wallets",
        "suspicious_transactions",
        "wallets",
        ["wallet_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_suspicious_transactions_user_id",
        "suspicious_transactions",
        ["user_id"],
    )
    op.create_index(
        "ix_suspicious_transactions_wallet_id",
        "suspicious_transactions",
        ["wallet_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_suspicious_transactions_wallet_id", table_name="suspicious_transactions")
    op.drop_index("ix_suspicious_transactions_user_id", table_name="suspicious_transactions")
    op.drop_constraint(
        "fk_suspicious_transactions_wallet_id_wallets",
        "suspicious_transactions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_suspicious_transactions_user_id_users",
        "suspicious_transactions",
        type_="foreignkey",
    )
    op.drop_column("suspicious_transactions", "amount")
    op.drop_column("suspicious_transactions", "operation_type")
    op.drop_column("suspicious_transactions", "wallet_id")
    op.drop_column("suspicious_transactions", "user_id")
    op.alter_column(
        "suspicious_transactions",
        "transfer_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
