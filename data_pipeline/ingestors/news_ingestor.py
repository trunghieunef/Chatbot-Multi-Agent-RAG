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
import json
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
from app.models import Article, ArticleImage, Chunk
from data_pipeline.clean import row_to_article
from data_pipeline.embed import BGEEmbedder


ARTICLE_IMAGE_META_KEY = "_image_urls"


def article_image_urls_from_row(row: dict[str, Any]) -> list[str]:
    raw = row.get("image_urls") or ""
    if not raw:
        return []
    if isinstance(raw, list):
        values = raw
    else:
        text = str(raw).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            values = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            values = [part.strip() for part in text.replace("\n", ",").split(",")]

    urls: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = str(value).strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def prepare_article_image_rows(
    article: Article,
    image_urls: list[str],
    *,
    source: str = "batdongsan",
) -> list[dict[str, Any]]:
    return [
        {
            "article_id": article.id,
            "article_url": article.url,
            "image_url": image_url,
            "sort_order": index,
            "is_primary": index == 0,
            "source": source,
        }
        for index, image_url in enumerate(image_urls)
    ]


async def replace_article_images(
    session,
    article: Article,
    image_urls: list[str],
) -> None:
    await session.execute(delete(ArticleImage).where(ArticleImage.article_id == article.id))
    if image_urls:
        session.add_all(
            ArticleImage(**image_row)
            for image_row in prepare_article_image_rows(article, image_urls)
        )


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


def empty_ingest_result() -> dict[str, int]:
    return {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


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


async def publish_article_batch(articles_data: list[dict[str, Any]]) -> list[Article]:
    persisted: list[Article] = []
    async with async_session() as session:
        for article_data in articles_data:
            image_urls = list(article_data.get(ARTICLE_IMAGE_META_KEY) or [])
            article_payload = {
                key: value
                for key, value in article_data.items()
                if key != ARTICLE_IMAGE_META_KEY
            }
            article = await upsert_article(session, article_payload)
            await replace_article_images(session, article, image_urls)
            persisted.append(article)
        await session.commit()
    return persisted


async def index_article_batch(
    articles_with_chunks: list[tuple[Article, list[dict[str, Any]]]],
    *,
    embedder: Any,
) -> dict[str, int]:
    if not articles_with_chunks:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    flat_texts = [
        chunk["text"]
        for _, chunks in articles_with_chunks
        for chunk in chunks
    ]
    if not flat_texts:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    try:
        flat_vectors = await embedder.embed_texts(flat_texts)
    except Exception as exc:
        print(f"[news-ingest] semantic index embed batch failed: {exc}", file=sys.stderr)
        return {
            "indexed": 0,
            "chunks": 0,
            "index_errors": len(articles_with_chunks),
        }

    cursor = 0
    indexed = 0
    chunks_inserted = 0
    index_errors = 0

    async with async_session() as session:
        for article, chunks in articles_with_chunks:
            count = len(chunks)
            vectors = flat_vectors[cursor : cursor + count]
            cursor += count
            try:
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
                indexed += 1
                chunks_inserted += len(chunks)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                index_errors += 1
                print(
                    f"[news-ingest] semantic index db write failed for {article.url}: {exc}",
                    file=sys.stderr,
                )
        await session.commit()

    return {"indexed": indexed, "chunks": chunks_inserted, "index_errors": index_errors}


async def ensure_vector_extension() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def ingest_article_rows(
    rows: list[dict[str, str]], batch_size: int = 25
) -> dict[str, int]:
    """Run the 3-phase batched ingest pipeline over ``rows``."""
    settings = get_settings()
    embedder = BGEEmbedder(
        model_name=settings.HF_EMBEDDING_MODEL,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        embedding_dim=settings.EMBEDDING_DIM,
        device=settings.HF_EMBEDDING_DEVICE or None,
    )

    # pgvector is infrastructure (not schema). Schema lives in Alembic migrations.
    await ensure_vector_extension()
    result = empty_ingest_result()

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]

        # Phase 1: clean structured article data.
        prepared: list[dict[str, Any]] = []
        for row in batch:
            try:
                article_data = row_to_article(row)
                if not article_data.get("url"):
                    continue
                article_data[ARTICLE_IMAGE_META_KEY] = article_image_urls_from_row(row)
                prepared.append(article_data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result["publish_errors"] += 1
                print(
                    f"[news-ingest] clean failed for {row.get('url', '?')}: {exc}",
                    file=sys.stderr,
                )

        if not prepared:
            continue

        try:
            persisted = await publish_article_batch(prepared)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result["publish_errors"] += len(prepared)
            print(f"[news-ingest] publish batch failed: {exc}", file=sys.stderr)
            continue

        result["published"] += len(persisted)

        articles_with_chunks: list[tuple[Article, list[dict[str, Any]]]] = []
        for article, article_data in zip(persisted, prepared, strict=True):
            try:
                chunks = build_article_chunks(article_data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result["index_errors"] += 1
                print(
                    f"[news-ingest] semantic index chunk build failed for {article.url}: {exc}",
                    file=sys.stderr,
                )
                continue
            articles_with_chunks.append((article, chunks))

        index_result = await index_article_batch(articles_with_chunks, embedder=embedder)
        result["indexed"] += index_result["indexed"]
        result["chunks"] += index_result["chunks"]
        result["index_errors"] += index_result["index_errors"]

    return result


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
