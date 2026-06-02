"""Load tinixai/vietnam-real-estates rows into PostgreSQL.

Usage:
    python backend/scripts/load_hf_real_estates.py --limit 200000
    python backend/scripts/load_hf_real_estates.py --all
    cd backend && python scripts/load_hf_real_estates.py --limit 200000
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Sequence


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.database import Base, async_session, engine
from app.models import Listing
from app.services.rag.ingest import hf_row_to_listing_data


DATASET_NAME = "tinixai/vietnam-real-estates"
MAX_ASYNCPG_QUERY_PARAMETERS = 32_767


async def _ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)


def _chunk_rows_for_insert(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not rows:
        return []

    parameter_count = max(len(row) for row in rows)
    safe_chunk_size = max(MAX_ASYNCPG_QUERY_PARAMETERS // parameter_count, 1)
    return [rows[index : index + safe_chunk_size] for index in range(0, len(rows), safe_chunk_size)]


async def _insert_batch(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    inserted = 0
    for chunk in _chunk_rows_for_insert(rows):
        async with async_session() as session:
            statement = pg_insert(Listing).values(chunk)
            statement = statement.on_conflict_do_nothing(index_elements=[Listing.product_id])
            result = await session.execute(statement)
            await session.commit()
            inserted += max(result.rowcount or 0, 0)
    return inserted


def _validate_embedding_mode(with_embeddings: bool) -> None:
    if not with_embeddings:
        return
    settings = get_settings()
    raise RuntimeError(
        "Listing.embedding da bi loai bo. Hay ingest embeddings qua chunks bang "
        f"{settings.EMBEDDING_PROVIDER}/{settings.HF_EMBEDDING_MODEL}."
    )


async def load_dataset(limit: int | None, batch_size: int, with_embeddings: bool = False) -> None:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Thieu dependency datasets/pyarrow. Hay cai backend requirements.") from exc

    if limit is not None and limit < 0:
        raise ValueError("--limit phai >= 0.")
    if batch_size <= 0:
        raise ValueError("--batch-size phai lon hon 0.")

    await _ensure_schema()
    _validate_embedding_mode(with_embeddings)

    dataset = load_dataset(DATASET_NAME, split="train", streaming=True)
    batch: list[dict[str, Any]] = []
    inserted = 0
    seen = 0

    for row_index, row in enumerate(dataset):
        if limit and row_index >= limit:
            break

        listing_data = hf_row_to_listing_data(dict(row), row_index=row_index)
        batch.append(listing_data)
        seen += 1

        if len(batch) >= batch_size:
            inserted += await _insert_batch(batch)
            print(f"Processed {seen} rows; inserted {inserted} new rows")
            batch = []

    inserted += await _insert_batch(batch)
    print(f"Done. Processed {seen} rows; inserted {inserted} new rows")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Load {DATASET_NAME} into PostgreSQL.")
    parser.add_argument(
        "--limit",
        type=int,
        default=200_000,
        help="Maximum rows to read from the train split. Use 0 for all rows.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Read the full train split. Equivalent to --limit 0.",
    )
    parser.add_argument("--batch-size", type=int, default=1_000, help="Database insert batch size.")
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Deprecated. Use chunk ingestors for BGE-M3 embeddings.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    limit = None if args.all or args.limit == 0 else args.limit
    asyncio.run(
        load_dataset(
            limit=limit,
            batch_size=args.batch_size,
            with_embeddings=args.with_embeddings,
        )
    )


if __name__ == "__main__":
    main()
