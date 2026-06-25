from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import Base, async_session, engine
from app.models import MarketPriceSnapshot


DATASET_NAME = "tinixai/vietnam-real-estates"
SOURCE_NAME = DATASET_NAME
INTERNAL_LISTINGS_SOURCE_NAME = "internal:listings"
MAX_ASYNCPG_QUERY_PARAMETERS = 32_767


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text_value = str(value).strip()
    if text_value.lower() in {"nan", "none", "null"}:
        return ""
    return text_value


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").strip()
        if not value:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number


def _parse_month(value: Any) -> date | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    if text_value.endswith("Z"):
        text_value = text_value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text_value)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text_value[:19], fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return date(parsed.year, parsed.month, 1)


def _parse_listing_month(value: Any) -> date | None:
    text_value = _clean_text(value)
    if not text_value:
        return None
    parsed_month = _parse_month(text_value)
    if parsed_month is not None:
        return parsed_month
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M"):
        try:
            parsed = datetime.strptime(text_value[:16], fmt)
        except ValueError:
            continue
        return date(parsed.year, parsed.month, 1)
    return None


def _price_to_vnd(price: Any, unit: Any) -> float | None:
    value = _to_float(price)
    if value is None:
        return None
    unit_text = _clean_text(unit).lower()
    if "billion" in unit_text or "tỷ" in unit_text or "ty" in unit_text:
        return value * 1_000_000_000
    if "million" in unit_text or "triệu" in unit_text or "trieu" in unit_text:
        return value * 1_000_000
    if value < 10_000:
        return value * 1_000_000_000
    return value


def _price_per_m2_to_vnd(value: Any, *, price_vnd: float, area: float) -> float | None:
    price_per_m2 = _to_float(value)
    if price_per_m2 is None:
        return price_vnd / area
    if price_per_m2 < 10_000:
        return price_per_m2 * 1_000_000
    return price_per_m2


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def normalize_hf_market_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one Hugging Face listing row into the snapshot input shape."""
    city = _clean_text(row.get("province_name"))
    district = _clean_text(row.get("district_name"))
    property_type = _clean_text(row.get("property_type_name"))
    month = _parse_month(row.get("published_at"))
    price = _to_float(row.get("price"))
    area = _to_float(row.get("area"))

    if not city or not district or not property_type or month is None:
        return None
    if price is None or area is None:
        return None

    return {
        "city": city,
        "district": district,
        "ward": _clean_text(row.get("ward_name")),
        "street": _clean_text(row.get("street_name")),
        "property_type": property_type,
        "month": month,
        "price": price,
        "area": area,
        "price_per_m2": price / area,
    }


def normalize_listing_market_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one internal Listing row into the snapshot input shape."""
    if _clean_text(row.get("listing_type")) != "sale":
        return None
    if row.get("is_active") is False:
        return None

    city = _clean_text(row.get("city"))
    district = _clean_text(row.get("district"))
    property_type = _clean_text(row.get("property_type"))
    month = _parse_listing_month(row.get("post_date"))
    price_vnd = _price_to_vnd(row.get("price"), row.get("price_unit"))
    area = _to_float(row.get("area"))

    if not city or not district or not property_type or month is None:
        return None
    if price_vnd is None or area is None:
        return None

    price_per_m2 = _price_per_m2_to_vnd(row.get("price_per_m2"), price_vnd=price_vnd, area=area)
    if price_per_m2 is None:
        return None

    return {
        "city": city,
        "district": district,
        "ward": _clean_text(row.get("ward")),
        # Internal listings have no dedicated street column (only a free-text
        # address), so the street segment is left empty for this source.
        "street": "",
        "property_type": property_type,
        "month": month,
        "price": price_vnd,
        "area": area,
        "price_per_m2": price_per_m2,
    }


def aggregate_market_snapshots(
    rows: Iterable[dict[str, Any]],
    *,
    source: str = SOURCE_NAME,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str, str, str, str, date], dict[str, list[float]]] = defaultdict(
        lambda: {"prices": [], "prices_per_m2": []}
    )

    for row in rows:
        key = (
            str(row["city"]),
            str(row["district"]),
            str(row.get("ward") or ""),
            str(row.get("street") or ""),
            str(row["property_type"]),
            row["month"],
        )
        buckets[key]["prices"].append(float(row["price"]))
        buckets[key]["prices_per_m2"].append(float(row["price_per_m2"]))

    snapshots: list[dict[str, Any]] = []
    for (city, district, ward, street, property_type, month), values in sorted(buckets.items()):
        prices = values["prices"]
        prices_per_m2 = values["prices_per_m2"]
        snapshots.append(
            {
                "city": city,
                "district": district,
                "ward": ward,
                "street": street,
                "property_type": property_type,
                "month": month,
                "period": month.strftime("%Y-%m"),
                "listing_count": len(prices),
                "avg_price": mean(prices),
                "median_price": median(prices),
                "avg_price_per_m2": mean(prices_per_m2),
                "median_price_per_m2": median(prices_per_m2),
                "p25_price_per_m2": _percentile(prices_per_m2, 0.25),
                "p75_price_per_m2": _percentile(prices_per_m2, 0.75),
                "source": source,
            }
        )
    return snapshots


async def _ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
        await conn.run_sync(Base.metadata.create_all)


def _chunk_rows_for_insert(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not rows:
        return []
    parameter_count = max(len(row) for row in rows)
    safe_chunk_size = max(MAX_ASYNCPG_QUERY_PARAMETERS // parameter_count, 1)
    return [rows[index : index + safe_chunk_size] for index in range(0, len(rows), safe_chunk_size)]


async def upsert_market_snapshots(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0

    written = 0
    for chunk in _chunk_rows_for_insert(rows):
        async with async_session() as session:
            statement = pg_insert(MarketPriceSnapshot).values(chunk)
            update_columns = {
                "period": statement.excluded.period,
                "listing_count": statement.excluded.listing_count,
                "avg_price": statement.excluded.avg_price,
                "median_price": statement.excluded.median_price,
                "avg_price_per_m2": statement.excluded.avg_price_per_m2,
                "median_price_per_m2": statement.excluded.median_price_per_m2,
                "p25_price_per_m2": statement.excluded.p25_price_per_m2,
                "p75_price_per_m2": statement.excluded.p75_price_per_m2,
            }
            statement = statement.on_conflict_do_update(
                constraint="uq_market_price_snapshot_segment",
                set_=update_columns,
            )
            result = await session.execute(statement)
            await session.commit()
            written += max(result.rowcount or 0, 0)
    return written


async def ingest_hf_market_snapshots(limit: int | None, batch_size: int = 1_000) -> dict[str, int]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Missing dependency datasets/pyarrow for Hugging Face ingestion.") from exc

    await _ensure_schema()
    dataset = load_dataset(DATASET_NAME, split="train", streaming=True)
    normalized_rows: list[dict[str, Any]] = []
    scanned = 0
    accepted = 0

    for row in dataset:
        if limit is not None and scanned >= limit:
            break
        scanned += 1
        normalized = normalize_hf_market_row(dict(row))
        if normalized is None:
            continue
        normalized_rows.append(normalized)
        accepted += 1

    snapshots = aggregate_market_snapshots(normalized_rows)
    written = 0
    for chunk in [snapshots[index : index + batch_size] for index in range(0, len(snapshots), batch_size)]:
        written += await upsert_market_snapshots(chunk)

    return {
        "scanned": scanned,
        "accepted": accepted,
        "snapshots": len(snapshots),
        "written": written,
    }


async def ingest_listing_market_snapshots(batch_size: int = 1_000) -> dict[str, int]:
    await _ensure_schema()
    async with async_session() as session:
        result = await session.execute(
            text(
                """
                SELECT listing_type, is_active, city, district, ward, property_type,
                       price, price_unit, price_per_m2, area, post_date
                FROM listings
                WHERE listing_type = 'sale'
                  AND is_active = true
                  AND city IS NOT NULL
                  AND district IS NOT NULL
                  AND property_type IS NOT NULL
                  AND price IS NOT NULL
                  AND area IS NOT NULL
                """
            )
        )
        listing_rows = [dict(row._mapping) for row in result.all()]

    normalized_rows = [
        normalized
        for row in listing_rows
        if (normalized := normalize_listing_market_row(row)) is not None
    ]
    snapshots = aggregate_market_snapshots(
        normalized_rows,
        source=INTERNAL_LISTINGS_SOURCE_NAME,
    )
    written = 0
    for chunk in [snapshots[index : index + batch_size] for index in range(0, len(snapshots), batch_size)]:
        written += await upsert_market_snapshots(chunk)

    return {
        "scanned": len(listing_rows),
        "accepted": len(normalized_rows),
        "snapshots": len(snapshots),
        "written": written,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Ingest market snapshots from {DATASET_NAME}.")
    parser.add_argument("--limit", type=int, default=100_000, help="Rows to scan. Use 0 for full dataset.")
    parser.add_argument("--all", action="store_true", help="Scan the full train split.")
    parser.add_argument("--batch-size", type=int, default=1_000, help="Snapshot upsert batch size.")
    parser.add_argument(
        "--source",
        choices=("hf", "listings", "both"),
        default="hf",
        help="Source to aggregate into market snapshots.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    limit = None if args.all or args.limit == 0 else args.limit
    if args.source == "listings":
        result = asyncio.run(ingest_listing_market_snapshots(batch_size=args.batch_size))
    elif args.source == "both":
        hf_result = asyncio.run(ingest_hf_market_snapshots(limit=limit, batch_size=args.batch_size))
        listing_result = asyncio.run(ingest_listing_market_snapshots(batch_size=args.batch_size))
        result = {"hf": hf_result, "listings": listing_result}
    else:
        result = asyncio.run(ingest_hf_market_snapshots(limit=limit, batch_size=args.batch_size))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
