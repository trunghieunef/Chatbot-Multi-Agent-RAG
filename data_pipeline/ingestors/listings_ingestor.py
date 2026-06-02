from __future__ import annotations

import argparse
import asyncio
import csv
import os
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
from app.models import Chunk, Listing
from data_pipeline.chunk import build_listing_chunks
from data_pipeline.clean import row_to_listing
from data_pipeline.embed import BGEEmbedder
from data_pipeline.enrich import GeminiIntentExtractor, build_geocoder


def read_csv_rows(csv_path: str) -> list[dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def prepare_listing_chunks(
    listing_id: int,
    chunks: list[dict[str, Any]],
    vectors: list[list[float]],
) -> list[dict[str, Any]]:
    if len(chunks) != len(vectors):
        raise ValueError("chunk/vector count mismatch")
    return [
        {
            "parent_type": "listing",
            "parent_id": listing_id,
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "embedding": vector,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


def empty_ingest_result() -> dict[str, int]:
    return {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


async def enrich_listing_data(listing: dict, *, geocoder, intent_extractor) -> dict:
    """Geocode the listing address and attach intent tags.

    Returns a copy of ``listing`` with ``latitude``/``longitude`` populated when
    the address is non-blank and the geocoder resolves it, plus ``intent_tags``
    produced by ``intent_extractor`` from a concatenation of title, description,
    and address. Geocoder/intent network failures degrade to ``None``/``[]`` so
    a flaky upstream service can't drop the listing from ingestion.
    """
    enriched = dict(listing)

    enriched.setdefault("latitude", None)
    enriched.setdefault("longitude", None)

    address = (enriched.get("address") or "").strip()
    if address:
        try:
            coord = await geocoder.geocode(address)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(
                f"[enrich] geocode failed for {address!r}: {exc}",
                file=sys.stderr,
            )
            coord = None
        if coord:
            enriched["latitude"], enriched["longitude"] = coord

    description_for_intent = " ".join(
        part
        for part in (enriched.get("title"), enriched.get("description"), enriched.get("address"))
        if part
    )
    try:
        enriched["intent_tags"] = await intent_extractor.extract(description_for_intent)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        print(
            f"[enrich] intent extraction failed for {enriched.get('product_id', '?')}: {exc}",
            file=sys.stderr,
        )
        enriched["intent_tags"] = []
    return enriched


async def upsert_listing(session, listing_data: dict[str, Any]) -> Listing:
    product_id = listing_data["product_id"]
    result = await session.execute(select(Listing).where(Listing.product_id == product_id))
    listing = result.scalar_one_or_none()

    if listing is None:
        listing = Listing(**listing_data)
        session.add(listing)
        await session.flush()
        return listing

    for key, value in listing_data.items():
        setattr(listing, key, value)
    await session.flush()
    return listing


async def publish_listing_batch(
    listings_data: list[dict[str, Any]],
) -> list[Listing]:
    persisted: list[Listing] = []
    async with async_session() as session:
        for listing_data in listings_data:
            listing = await upsert_listing(session, listing_data)
            persisted.append(listing)
        await session.commit()
    return persisted


async def index_listing_batch(
    listings_with_chunks: list[tuple[Listing, list[dict[str, Any]]]],
    *,
    embedder: Any,
) -> dict[str, int]:
    if not listings_with_chunks:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    flat_texts = [
        chunk["text"]
        for _, chunks in listings_with_chunks
        for chunk in chunks
    ]
    if not flat_texts:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    try:
        flat_vectors = await embedder.embed_texts(flat_texts)
    except Exception as exc:
        print(f"[ingest] semantic index embed batch failed: {exc}", file=sys.stderr)
        return {
            "indexed": 0,
            "chunks": 0,
            "index_errors": len(listings_with_chunks),
        }

    cursor = 0
    indexed = 0
    chunks_inserted = 0
    index_errors = 0

    async with async_session() as session:
        for listing, chunks in listings_with_chunks:
            count = len(chunks)
            vectors = flat_vectors[cursor : cursor + count]
            cursor += count
            try:
                chunk_rows = prepare_listing_chunks(listing.id, chunks, vectors)
                await session.execute(
                    delete(Chunk).where(
                        Chunk.parent_type == "listing",
                        Chunk.parent_id == listing.id,
                    )
                )
                session.add_all([Chunk(**chunk_row) for chunk_row in chunk_rows])
                indexed += 1
                chunks_inserted += len(chunk_rows)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                index_errors += 1
                print(
                    f"[ingest] semantic index db write failed for {listing.product_id}: {exc}",
                    file=sys.stderr,
                )
        await session.commit()

    return {
        "indexed": indexed,
        "chunks": chunks_inserted,
        "index_errors": index_errors,
    }


async def ensure_vector_extension() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


async def ingest_listing_rows(rows: list[dict[str, str]], batch_size: int = 50) -> dict[str, int]:
    settings = get_settings()
    embedder = BGEEmbedder(
        model_name=settings.HF_EMBEDDING_MODEL,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        embedding_dim=settings.EMBEDDING_DIM,
        device=settings.HF_EMBEDDING_DEVICE or None,
    )

    geocoder = build_geocoder(
        provider=settings.GEOCODER_PROVIDER,
        user_agent=settings.GEOCODER_USER_AGENT,
        goong_api_key=settings.GOONG_API_KEY,
    )
    if settings.INTENT_EXTRACTOR == "gemini" and settings.GEMINI_API_KEY:
        intent_extractor = GeminiIntentExtractor(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_INTENT_MODEL,
        )
    else:
        class _NoOpIntent:
            async def extract(self, _content):
                return []
        intent_extractor = _NoOpIntent()

    # pgvector is infrastructure (not schema). Schema lives in Alembic migrations.
    await ensure_vector_extension()

    result = empty_ingest_result()

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]

        # Phase 1: clean + enrich structured listing data.
        prepared: list[dict[str, Any]] = []
        for row in batch:
            try:
                listing_data = row_to_listing(row)
                if not listing_data.get("product_id"):
                    continue
                listing_data = await enrich_listing_data(
                    listing_data,
                    geocoder=geocoder,
                    intent_extractor=intent_extractor,
                )
                prepared.append(listing_data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result["publish_errors"] += 1
                print(
                    f"[ingest] clean/enrich failed for {row.get('product_id', '?')}: {exc}",
                    file=sys.stderr,
                )

        if not prepared:
            continue

        try:
            persisted = await publish_listing_batch(prepared)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result["publish_errors"] += len(prepared)
            print(f"[ingest] publish batch failed: {exc}", file=sys.stderr)
            continue

        result["published"] += len(persisted)

        listings_with_chunks: list[tuple[Listing, list[dict[str, Any]]]] = []
        for listing, listing_data in zip(persisted, prepared, strict=True):
            try:
                chunks = build_listing_chunks(listing_data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result["index_errors"] += 1
                print(
                    f"[ingest] semantic index chunk build failed for {listing.product_id}: {exc}",
                    file=sys.stderr,
                )
                continue
            listings_with_chunks.append((listing, chunks))

        index_result = await index_listing_batch(listings_with_chunks, embedder=embedder)
        result["indexed"] += index_result["indexed"]
        result["chunks"] += index_result["chunks"]
        result["index_errors"] += index_result["index_errors"]

    return result


async def load_csv_to_db(csv_path: str, batch_size: int = 50) -> dict[str, int]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(csv_path)
    rows = read_csv_rows(csv_path)
    return await ingest_listing_rows(rows, batch_size=batch_size)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest listing CSV into PostgreSQL chunks")
    parser.add_argument("--csv", required=True, help="Path to listing details CSV")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    result = await load_csv_to_db(args.csv, args.batch_size)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
