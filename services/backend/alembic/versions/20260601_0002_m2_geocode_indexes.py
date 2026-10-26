"""m2 geocode and project indexes

Revision ID: 20260601_0002
Revises: 20260525_0001
Create Date: 2026-06-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260601_0002"
down_revision: Union[str, None] = "20260525_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_listings_city_district", "listings", ["city", "district"], unique=False)
    op.create_index("ix_listings_lat_lon", "listings", ["latitude", "longitude"], unique=False)
    op.create_index("ix_projects_city_district", "projects", ["city", "district"], unique=False)
    op.create_index("ix_articles_post_date", "articles", ["post_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_articles_post_date", table_name="articles")
    op.drop_index("ix_projects_city_district", table_name="projects")
    op.drop_index("ix_listings_lat_lon", table_name="listings")
    op.drop_index("ix_listings_city_district", table_name="listings")
