"""Persist idempotent UTC daily-limit reset runs."""

from alembic import op
import sqlalchemy as sa


revision = "0010_daily_limit_resets"
down_revision = "0009_roles_refund_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_limit_resets",
        sa.Column("reset_date", sa.Date(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "strategy",
            sa.String(length=32),
            nullable=False,
            server_default="UTC_CALENDAR_DAY",
        ),
        sa.PrimaryKeyConstraint("reset_date"),
    )


def downgrade() -> None:
    op.drop_table("daily_limit_resets")
