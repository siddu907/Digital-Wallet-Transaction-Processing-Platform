"""Add unique operation references to suspicious events."""

from alembic import op
import sqlalchemy as sa


revision = "0008_suspicious_op_ref"
down_revision = "0007_generic_risk_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suspicious_transactions",
        sa.Column("operation_id", sa.String(length=36), nullable=True),
    )
    op.create_unique_constraint(
        "uq_suspicious_operation",
        "suspicious_transactions",
        ["operation_type", "operation_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_suspicious_operation",
        "suspicious_transactions",
        type_="unique",
    )
    op.drop_column("suspicious_transactions", "operation_id")
