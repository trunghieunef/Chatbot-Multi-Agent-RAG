"""add article and project image urls tables

Revision ID: 20260801_0010
Revises: 20260801_0009
Create Date: 2026-08-01 00:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0010"
down_revision: Union[str, None] = "20260801_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("article_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_article_images_article_id"), "article_images", ["article_id"], unique=False)
    op.create_index(op.f("ix_article_images_article_url"), "article_images", ["article_url"], unique=False)
    op.create_index("ix_article_images_article_order", "article_images", ["article_id", "sort_order"], unique=False)
    op.create_index("ix_article_images_url_order", "article_images", ["article_url", "sort_order"], unique=False)

    op.create_table(
        "project_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_slug", sa.String(length=255), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_images_project_id"), "project_images", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_images_project_slug"), "project_images", ["project_slug"], unique=False)
    op.create_index("ix_project_images_project_order", "project_images", ["project_id", "sort_order"], unique=False)
    op.create_index("ix_project_images_slug_order", "project_images", ["project_slug", "sort_order"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_project_images_slug_order", table_name="project_images")
    op.drop_index("ix_project_images_project_order", table_name="project_images")
    op.drop_index(op.f("ix_project_images_project_slug"), table_name="project_images")
    op.drop_index(op.f("ix_project_images_project_id"), table_name="project_images")
    op.drop_table("project_images")
    op.drop_index("ix_article_images_url_order", table_name="article_images")
    op.drop_index("ix_article_images_article_order", table_name="article_images")
    op.drop_index(op.f("ix_article_images_article_url"), table_name="article_images")
    op.drop_index(op.f("ix_article_images_article_id"), table_name="article_images")
    op.drop_table("article_images")
