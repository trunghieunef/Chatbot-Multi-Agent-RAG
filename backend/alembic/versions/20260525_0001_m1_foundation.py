"""m1 foundation schema

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "20260525_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=150), nullable=True),
        sa.Column("post_date", sa.Date(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index(op.f("ix_articles_category"), "articles", ["category"], unique=False)

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_type", sa.String(length=30), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(length=50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chunks_parent", "chunks", ["parent_type", "parent_id"], unique=False)
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks", postgresql_using="hnsw")
    op.drop_index("ix_chunks_parent", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_articles_category"), table_name="articles")
    op.drop_table("articles")
