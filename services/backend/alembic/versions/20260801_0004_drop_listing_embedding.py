"""drop legacy listings.embedding column

Revision ID: 20260801_0004
Revises: 20260701_0003
Create Date: 2026-08-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision: str = "20260801_0004"
down_revision: Union[str, None] = "20260701_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("listings", "embedding")


def downgrade() -> None:
    op.add_column("listings", sa.Column("embedding", Vector(dim=768), nullable=True))
