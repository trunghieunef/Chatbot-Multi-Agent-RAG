"""add market price snapshot table

Revision ID: 20260801_0009
Revises: 20260801_0008
Create Date: 2026-06-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260801_0009"
down_revision = "20260801_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.create_table(
        "market_price_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("district", sa.String(length=100), nullable=False),
        sa.Column("ward", sa.String(length=100), nullable=False),
        sa.Column("property_type", sa.String(length=120), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("listing_count", sa.Integer(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=True),
        sa.Column("median_price", sa.Float(), nullable=True),
        sa.Column("avg_price_per_m2", sa.Float(), nullable=True),
        sa.Column("median_price_per_m2", sa.Float(), nullable=True),
        sa.Column("p25_price_per_m2", sa.Float(), nullable=True),
        sa.Column("p75_price_per_m2", sa.Float(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=150),
            nullable=False,
            server_default="tinixai/vietnam-real-estates",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "city",
            "district",
            "ward",
            "property_type",
            "month",
            "source",
            name="uq_market_price_snapshot_segment",
        ),
    )
    op.create_index(
        "ix_market_snapshot_city_district",
        "market_price_snapshots",
        ["city", "district"],
        unique=False,
    )
    op.create_index(
        "ix_market_snapshot_month",
        "market_price_snapshots",
        ["month"],
        unique=False,
    )
    op.create_index(
        "ix_market_snapshot_property_type",
        "market_price_snapshots",
        ["property_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_market_snapshot_property_type", table_name="market_price_snapshots")
    op.drop_index("ix_market_snapshot_month", table_name="market_price_snapshots")
    op.drop_index("ix_market_snapshot_city_district", table_name="market_price_snapshots")
    op.drop_table("market_price_snapshots")
