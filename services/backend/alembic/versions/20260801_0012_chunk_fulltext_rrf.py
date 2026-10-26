"""add full-text tsvector on chunks for hybrid (RRF) retrieval

Adds a generated ``text_tsv`` column + GIN index on ``chunks`` so lexical
(full-text) search can run alongside pgvector kNN and be fused via Reciprocal
Rank Fusion. Vietnamese is handled with the ``simple`` config over an
accent-stripped text via an IMMUTABLE ``f_unaccent`` wrapper (the built-in
1-arg ``unaccent`` is only STABLE and cannot be used in a generated column /
index expression).

Revision ID: 20260801_0012
Revises: 20260801_0011
Create Date: 2026-06-24 00:00:00.000000
"""

from alembic import op


revision = "20260801_0012"
down_revision = "20260801_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # IMMUTABLE wrapper: the 2-arg unaccent(regdictionary, text) with a
    # schema-qualified dictionary is immutable, unlike the search-path-dependent
    # 1-arg form. Required for use in a generated column / index expression.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.f_unaccent(text)
            RETURNS text
            LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS
        $func$
            SELECT public.unaccent('public.unaccent', $1)
        $func$
        """
    )

    op.execute(
        """
        ALTER TABLE chunks
            ADD COLUMN IF NOT EXISTS text_tsv tsvector
            GENERATED ALWAYS AS (
                to_tsvector('simple', public.f_unaccent(coalesce(text, '')))
            ) STORED
        """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_text_tsv "
        "ON chunks USING gin (text_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_text_tsv")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS text_tsv")
    op.execute("DROP FUNCTION IF EXISTS public.f_unaccent(text)")
