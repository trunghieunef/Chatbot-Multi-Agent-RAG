"""pipeline runs summary table

Revision ID: 20260801_0005
Revises: 20260801_0004
Create Date: 2026-08-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260801_0005"
down_revision: Union[str, None] = "20260801_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dag_id", sa.String(length=80), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pipeline_runs_dag_run", "pipeline_runs", ["dag_id", "run_id"], unique=True)
    op.create_index("ix_pipeline_runs_started", "pipeline_runs", ["started_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_started", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_dag_run", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
