"""Add user token versions for immediate access-token revocation."""

from alembic import op
import sqlalchemy as sa


revision = "0003_user_auth_token_version"
down_revision = "0002_outbox_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "auth_token_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "auth_token_version")
