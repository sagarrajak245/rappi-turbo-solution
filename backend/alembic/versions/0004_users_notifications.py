"""users, notifications, agent_runs.decided_by

Revision ID: 0004
Revises: 0002
Create Date: 2026-10-14 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | Sequence[str] | None = "0002"  # rebased onto 0003 at integration
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=200), nullable=False),
        sa.Column(
            "role",
            sa.Enum("buyer", "admin", name="userrole", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("branch", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_runs.id"], name=op.f("fk_notifications_run_id_agent_runs")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notifications_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_notifications_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("decided_by", sa.String(length=32), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_agent_runs_decided_by_users"), "users", ["decided_by"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_runs", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_agent_runs_decided_by_users"), type_="foreignkey")
        batch_op.drop_column("decided_by")

    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notifications_user_id"))

    op.drop_table("notifications")
    op.drop_table("users")
