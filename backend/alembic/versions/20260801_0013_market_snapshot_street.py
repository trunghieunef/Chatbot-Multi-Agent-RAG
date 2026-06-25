"""add street segment to market price snapshots

Adds a ``street`` column to ``market_price_snapshots`` and extends the segment
unique constraint to include it, so snapshots are aggregated per street as well
as ward/district/city. HF rows carry ``street_name``; internal listings have no
street column and store an empty string.

Revision ID: 20260801_0013
Revises: 20260801_0012
Create Date: 2026-06-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_0013"
down_revision = "20260801_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_price_snapshots",
        sa.Column(
            "street",
            sa.String(length=150),
            nullable=False,
            server_default="",
        ),
    )
    op.drop_constraint(
        "uq_market_price_snapshot_segment",
        "market_price_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_market_price_snapshot_segment",
        "market_price_snapshots",
        ["city", "district", "ward", "street", "property_type", "month", "source"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_market_price_snapshot_segment",
        "market_price_snapshots",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_market_price_snapshot_segment",
        "market_price_snapshots",
        ["city", "district", "ward", "property_type", "month", "source"],
    )
    op.drop_column("market_price_snapshots", "street")
