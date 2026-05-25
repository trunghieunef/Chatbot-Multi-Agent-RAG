"""legal article metadata

Revision ID: 20260701_0003
Revises: 20260601_0002
Create Date: 2026-07-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_0003"
down_revision: Union[str, None] = "20260601_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "metadata_json")
