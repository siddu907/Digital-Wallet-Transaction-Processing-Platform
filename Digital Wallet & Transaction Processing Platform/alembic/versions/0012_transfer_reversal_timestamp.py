"""Track reversals separately from completed transfer status."""

from alembic import op
import sqlalchemy as sa


revision = "0012_transfer_reversal_timestamp"
down_revision = "0011_integer_entity_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("transfers")
    }
    if "reversed_at" not in existing_columns:
        op.add_column(
            "transfers",
            sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("transfers")
    }
    if "reversed_at" in existing_columns:
        op.drop_column("transfers", "reversed_at")
