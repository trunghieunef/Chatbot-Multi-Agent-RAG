"""legal article + chunk metadata

Revision ID: 20260701_0003
Revises: 20260601_0002
Create Date: 2026-07-01 00:00:00

Adds ``metadata_json`` (plain JSON, not JSONB - audit-only, not indexed) to
``articles`` and ``chunks``. The ``chunks.metadata_json`` field carries the
per-chunk citation payload produced by ``data_pipeline.legal.chunker`` so the
Legal Advisor can render Điều/Khoản references at query time.
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
    op.add_column("chunks", sa.Column("metadata_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "metadata_json")
    op.drop_column("articles", "metadata_json")
