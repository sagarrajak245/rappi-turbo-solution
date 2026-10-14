"""lessons

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 23:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "lessons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("node_code", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "active",
                "disabled",
                name="lessonstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("source_run_id", sa.String(length=32), nullable=True),
        sa.Column("times_applied", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["agent_runs.id"], name=op.f("fk_lessons_source_run_id_agent_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
    )
    with op.batch_alter_table("lessons", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_lessons_status"), ["status"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("lessons", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_lessons_status"))
    op.drop_table("lessons")
