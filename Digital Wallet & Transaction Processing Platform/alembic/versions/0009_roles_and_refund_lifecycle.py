"""Add role catalog and refund lifecycle timestamps."""

from alembic import op
import sqlalchemy as sa


revision = "0009_roles_refund_lifecycle"
down_revision = "0008_suspicious_op_ref"
branch_labels = None
depends_on = None

role_enum = sa.Enum(
    "SUPER_ADMIN",
    "ADMIN",
    "SUPPORT_AGENT",
    "CUSTOMER",
    name="role",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("name", role_enum, nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("name"),
    )
    op.execute(
        sa.text(
            "INSERT INTO roles (name, description) VALUES "
            "('SUPER_ADMIN', 'Full platform access'), "
            "('ADMIN', 'Administrative access'), "
            "('SUPPORT_AGENT', 'Customer support access'), "
            "('CUSTOMER', 'Wallet customer access')"
        )
    )
    op.create_foreign_key(
        "fk_users_role_roles",
        "users",
        "roles",
        ["role"],
        ["name"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "refunds",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refunds",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("refunds", "completed_at")
    op.drop_column("refunds", "reviewed_at")
    op.drop_constraint("fk_users_role_roles", "users", type_="foreignkey")
    op.drop_table("roles")
