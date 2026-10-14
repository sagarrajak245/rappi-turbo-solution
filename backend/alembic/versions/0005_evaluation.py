"""evaluation runs and results

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.String(length=20), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("eval_run_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.String(length=40), nullable=False),
        sa.Column("sku", sa.String(length=40), nullable=False),
        sa.Column("node", sa.String(length=20), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=False),
        sa.Column("actual", sa.JSON(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("hard_violations", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["eval_run_id"], ["eval_runs.id"], name=op.f("fk_eval_results_eval_run_id_eval_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_results")),
    )
    with op.batch_alter_table("eval_results", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_eval_results_eval_run_id"), ["eval_run_id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("eval_results", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_results_eval_run_id"))
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
