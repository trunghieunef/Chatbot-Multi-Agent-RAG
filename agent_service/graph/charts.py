"""Pure builders that turn already-fetched market data into chart specs.

No I/O — deterministic shaping of data the market tools already returned, so the
chatbot can render a price-trend line and a district-comparison bar in the bubble.
"""

from __future__ import annotations

from typing import Any

_DEFAULT_UNIT = "triệu VNĐ/m²"


def _to_float(value: Any) -> float | None:
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def build_price_trend_chart(
    timeseries: list[dict], *, title: str, unit: str = _DEFAULT_UNIT
) -> dict | None:
    """line_band spec from market timeseries rows (snapshot_month + avg/min/max).

    Returns None if fewer than 2 months have a numeric avg.
    """
    points: list[dict[str, Any]] = []
    for row in timeseries:
        month = row.get("snapshot_month")
        avg = _to_float(row.get("avg_price_per_m2"))
        if not month or avg is None:
            continue
        points.append(
            {
                "month": month,
                "avg": avg,
                "min": _to_float(row.get("min_price_per_m2")),
                "max": _to_float(row.get("max_price_per_m2")),
            }
        )
    if len(points) < 2:
        return None
    points.sort(key=lambda p: p["month"])
    return {"type": "line_band", "title": title, "unit": unit, "x_key": "month", "data": points}


def build_district_comparison_chart(
    metrics: list[dict], *, title: str, unit: str = _DEFAULT_UNIT
) -> dict | None:
    """bar spec comparing avg price/m² across districts (first value per district).

    Returns None if fewer than 2 distinct districts have a numeric value.
    """
    by_district: dict[str, float] = {}
    for item in metrics:
        location = item.get("location")
        district = location.get("district") if isinstance(location, dict) else None
        district = district or item.get("district")
        avg = _to_float(item.get("value"))
        if not district or avg is None or district in by_district:
            continue
        by_district[district] = avg
    if len(by_district) < 2:
        return None
    data = sorted(
        ({"district": d, "avg": a} for d, a in by_district.items()),
        key=lambda x: x["avg"],
        reverse=True,
    )
    return {"type": "bar", "title": title, "unit": unit, "x_key": "district", "data": data}


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tag_extreme(rows: list[dict], values: list[float | None], tag: str, *, want_min: bool) -> None:
    idxs = [i for i, v in enumerate(values) if isinstance(v, (int, float))]
    if not idxs:
        return
    best = (min if want_min else max)(idxs, key=lambda i: values[i])
    rows[best]["tags"].append(tag)


def build_comparison_table(
    listings: list[dict],
    *,
    area_avg_price_per_m2: float | None,
    unit: str = _DEFAULT_UNIT,
    auto_open: bool = False,
) -> dict | None:
    """Side-by-side comparison block for >=2 listings.

    Computes price_per_m2 (price in tỷ -> triệu/m²), within-set tags
    (cheapest / largest / best price-per-m²), and % vs the area average.
    ``auto_open`` tells the frontend to show the table expanded by default
    (set when the user explicitly asked to compare). Returns None for fewer
    than 2 listings.
    """
    if len(listings) < 2:
        return None

    prices: list[float | None] = []
    areas: list[float | None] = []
    ppms: list[float | None] = []
    rows: list[dict[str, Any]] = []

    for listing in listings:
        price = _num(listing.get("price"))
        area = _num(listing.get("area"))
        ppm = round(price * 1000 / area, 1) if price and area else None
        pct = (
            round((ppm - area_avg_price_per_m2) / area_avg_price_per_m2 * 100, 1)
            if ppm is not None and area_avg_price_per_m2
            else None
        )
        district = listing.get("district") or ""
        city = listing.get("city") or ""
        location = f"{district}, {city}" if district else city
        listing_id = listing.get("id")
        url = listing.get("url") or (f"/nha-dat-ban/{listing_id}" if listing_id else None)

        prices.append(price)
        areas.append(area)
        ppms.append(ppm)
        rows.append(
            {
                "title": listing.get("title"),
                "url": url,
                "price_text": listing.get("price_text"),
                "area_text": listing.get("area_text"),
                "price_per_m2": ppm,
                "bedrooms": listing.get("bedrooms"),
                "bathrooms": listing.get("bathrooms"),
                "legal_status": listing.get("legal_status"),
                "furniture": listing.get("furniture"),
                "location": location,
                "tags": [],
                "pct_vs_area_avg": pct,
            }
        )

    _tag_extreme(rows, prices, "Rẻ nhất", want_min=True)
    _tag_extreme(rows, areas, "Rộng nhất", want_min=False)
    _tag_extreme(rows, ppms, "Giá/m² tốt nhất", want_min=True)

    return {
        "type": "comparison_table",
        "title": f"So sánh {len(rows)} căn",
        "unit": unit,
        "area_avg_price_per_m2": area_avg_price_per_m2,
        "auto_open": auto_open,
        "rows": rows,
    }
