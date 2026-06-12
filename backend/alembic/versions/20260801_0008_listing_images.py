"""add listing image urls table

Revision ID: 20260801_0008
Revises: 20260801_0007
Create Date: 2026-08-01 00:08:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0008"
down_revision: Union[str, None] = "20260801_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "listing_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(length=50), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_listing_images_listing_id"), "listing_images", ["listing_id"], unique=False)
    op.create_index(op.f("ix_listing_images_product_id"), "listing_images", ["product_id"], unique=False)
    op.create_index("ix_listing_images_listing_order", "listing_images", ["listing_id", "sort_order"], unique=False)
    op.create_index("ix_listing_images_product_order", "listing_images", ["product_id", "sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_listing_images_product_order", table_name="listing_images")
    op.drop_index("ix_listing_images_listing_order", table_name="listing_images")
    op.drop_index(op.f("ix_listing_images_product_id"), table_name="listing_images")
    op.drop_index(op.f("ix_listing_images_listing_id"), table_name="listing_images")
    op.drop_table("listing_images")
