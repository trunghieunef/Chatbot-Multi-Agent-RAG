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
