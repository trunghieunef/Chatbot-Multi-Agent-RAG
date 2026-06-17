from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import update


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import async_session
from app.models import Listing
from data_pipeline.clean import row_to_listing
from data_pipeline.ingestors.listings_ingestor import (
    LISTING_IMAGE_META_KEY,
    listing_image_urls_from_row,
    publish_listing_batch,
)


def read_rows(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


async def deactivate_existing_listings() -> int:
    async with async_session() as session:
        result = await session.execute(update(Listing).values(is_active=False))
        await session.commit()
        return int(result.rowcount or 0)


async def activate_rows(rows: list[dict[str, str]]) -> int:
    listings_data = []
    for row in rows:
        listing_data = row_to_listing(row)
        if not listing_data.get("product_id"):
            continue
        listing_data[LISTING_IMAGE_META_KEY] = listing_image_urls_from_row(row)
        listings_data.append(listing_data)

    await publish_listing_batch(listings_data)
    return len(listings_data)


async def run(paths: list[Path], *, skip_deactivate: bool = False) -> dict[str, int]:
    rows = read_rows(paths)
    deactivated = 0 if skip_deactivate else await deactivate_existing_listings()
    activated = await activate_rows(rows)
    return {"deactivated": deactivated, "activated": activated}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deactivate existing listings and activate selected crawled listing CSV rows."
    )
    parser.add_argument("csv", nargs="+", type=Path)
    parser.add_argument("--skip-deactivate", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run(args.csv, skip_deactivate=args.skip_deactivate))
    print(result)


if __name__ == "__main__":
    main()
