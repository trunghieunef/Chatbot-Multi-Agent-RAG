"""switch chunks embeddings to bge-m3 1024 dimensions

Revision ID: 20260801_0007
Revises: 20260801_0006
Create Date: 2026-08-01 00:07:00

Existing chunk vectors were produced with Gemini at 768 dimensions. pgvector
cannot mix vector dimensions in the same column, so this migration clears
chunks and rebuilds the column/index for BAAI/bge-m3 dense vectors.
Re-ingest listings, projects, news, and legal KB after applying this migration.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260801_0007"
down_revision: Union[str, None] = "20260801_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("DELETE FROM chunks")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(1024)")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS embedding")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 128)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute("DELETE FROM chunks")
    op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(768)")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS embedding vector(768)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 128)"
    )
