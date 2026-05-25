"""Ingest crawled news article CSVs into PostgreSQL articles + chunks tables.

Mirrors the 3-phase batched flow used by listings_ingestor and projects_ingestor:

    Phase 1: clean + chunk in memory
    Phase 2: one embed call per batch
    Phase 3: persist within a single session per batch (upsert + delete + add_all)

Differences vs projects_ingestor:
    - Upsert key is ``url`` (not slug).
    - ``parent_type="article"`` in chunks.
    - Article body is split into overlapping windows (default 800/120) plus a
      separate "title" chunk.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import async_session, engine
from app.models import Article, Chunk
from data_pipeline.clean import row_to_article
from data_pipeline.embed import GeminiEmbedder


def build_article_chunks(
    article: dict, *, chunk_size: int = 800, overlap: int = 120
) -> list[dict[str, Any]]:
    """Split article body into overlapping chunks plus a single title chunk.

    Returns a list of ``{"chunk_type": str, "text": str}`` dicts in document
    order. The first entry (when present) is the ``title`` chunk; subsequent
    entries are ``body`` chunks of length ``<= chunk_size``, advancing by
    ``chunk_size - overlap`` characters per step. Empty/whitespace-only
    pieces are skipped. If ``body`` is empty, only the title chunk is
    returned (or an empty list if title is also empty).
    """
    chunks: list[dict[str, Any]] = []
    title = (article.get("title") or "").strip()
    body = (article.get("body") or "").strip()

    if title:
        chunks.append({"chunk_type": "title", "text": title})

    if not body:
        return chunks

    step = max(chunk_size - overlap, 1)
    for start in range(0, len(body), step):
        piece = body[start : start + chunk_size]
        if piece.strip():
            chunks.append({"chunk_type": "body", "text": piece})
        if start + chunk_size >= len(body):
            break
    return chunks


async def upsert_article(session, article_data: dict[str, Any]) -> Article:
    """Upsert by ``url`` and return the persisted Article row."""
    url = article_data["url"]
    result = await session.execute(select(Article).where(Article.url == url))
    article = result.scalar_one_or_none()
    if article is None:
        article = Article(**article_data)
        session.add(article)
        await session.flush()
        return article
    for key, value in article_data.items():
        setattr(article, key, value)
    await session.flush()
    return article


async def ingest_article_rows(
    rows: list[dict[str, str]], batch_size: int = 25
) -> dict[str, int]:
    """Run the 3-phase batched ingest pipeline over ``rows``."""
    settings = get_settings()
    embedder = GeminiEmbedder(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_EMBEDDING_MODEL,
        batch_size=100,
    )

    # pgvector is infrastructure (not schema). Schema lives in Alembic migrations.
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    inserted = 0
    chunks_inserted = 0
    errors = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]

        # Phase 1: clean + chunk in memory.
        prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for row in batch:
            try:
                article_data = row_to_article(row)
                if not article_data.get("url"):
                    continue
                chunks = build_article_chunks(article_data)
                if not chunks:
                    continue
                prepared.append((article_data, chunks))
            except Exception as exc:
                errors += 1
                print(
                    f"[news-ingest] clean/chunk failed for {row.get('url', '?')}: {exc}",
                    file=sys.stderr,
                )

        if not prepared:
            continue

        # Phase 2: one embed call per batch.
        flat_texts = [chunk["text"] for _, chunks in prepared for chunk in chunks]
        try:
            flat_vectors = await embedder.embed_texts(flat_texts)
        except Exception as exc:
            errors += len(prepared)
            print(f"[news-ingest] embed batch failed: {exc}", file=sys.stderr)
            continue

        cursor = 0
        with_vectors: list[
            tuple[dict[str, Any], list[dict[str, Any]], list[list[float]]]
        ] = []
        for article_data, chunks in prepared:
            count = len(chunks)
            with_vectors.append(
                (article_data, chunks, flat_vectors[cursor : cursor + count])
            )
            cursor += count

        # Phase 3: persist within a single session per batch.
        async with async_session() as session:
            for article_data, chunks, vectors in with_vectors:
                try:
                    article = await upsert_article(session, article_data)
                    await session.execute(
                        delete(Chunk).where(
                            Chunk.parent_type == "article",
                            Chunk.parent_id == article.id,
                        )
                    )
                    session.add_all(
                        [
                            Chunk(
                                parent_type="article",
                                parent_id=article.id,
                                chunk_type=chunk["chunk_type"],
                                text=chunk["text"],
                                embedding=vector,
                            )
                            for chunk, vector in zip(chunks, vectors, strict=True)
                        ]
                    )
                    inserted += 1
                    chunks_inserted += len(chunks)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    errors += 1
                    print(
                        f"[news-ingest] db write failed for {article_data.get('url', '?')}: {exc}",
                        file=sys.stderr,
                    )
            await session.commit()

    return {"articles": inserted, "chunks": chunks_inserted, "errors": errors}


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest article CSV into PostgreSQL chunks"
    )
    parser.add_argument("--csv", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()
    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    print(await ingest_article_rows(rows, batch_size=args.batch_size))


if __name__ == "__main__":
    asyncio.run(main())
