"""tune chunks hnsw index for larger corpus

Revision ID: 20260801_0006
Revises: 20260801_0005
Create Date: 2026-08-01 00:00:00

Recreates the HNSW index with ``ef_construction=128`` (up from 64) for
better recall on the larger M2/M3/M4 corpus, and sets the database-level
``hnsw.ef_search=80`` so new sessions get tuned query-time recall by
default.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0006"
down_revision: Union[str, None] = "20260801_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 128)"
    )
    # ``ALTER DATABASE CURRENT`` is unsupported on the asyncpg driver, so
    # resolve the database name explicitly. ``SET LOCAL`` would only apply
    # to this transaction; we want the default to stick for new sessions.
    bind = op.get_bind()
    db_name = bind.execute(sa.text("SELECT current_database()")).scalar()
    op.execute(sa.text(f'ALTER DATABASE "{db_name}" SET hnsw.ef_search = 80'))


def downgrade() -> None:
    bind = op.get_bind()
    db_name = bind.execute(sa.text("SELECT current_database()")).scalar()
    op.execute(sa.text(f'ALTER DATABASE "{db_name}" RESET hnsw.ef_search'))
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
