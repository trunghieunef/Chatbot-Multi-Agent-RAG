from __future__ import annotations

from typing import Any

from chatbot.tools.market_stats import district_price_overview


async def lookup_market_metrics(filters: dict[str, Any]) -> list[dict[str, Any]]:
    city = filters.get("city")
    listing_type = filters.get("listing_type") or "sale"
    property_type = filters.get("property_type")
    if not city:
        return []

    rows = await district_price_overview(
        city=str(city),
        listing_type=str(listing_type),
        property_type=str(property_type) if property_type else None,
    )
    return [
        {
            "source_identity": (
                f"market:{row.get('district')}:{property_type or 'all'}:"
                "avg_price_per_m2:current"
            ),
            "metric": "avg_price_per_m2",
            "value": row.get("avg_price_per_m2"),
            "unit": "million VND/m2",
            "location": {"city": city, "district": row.get("district")},
            "property_type": property_type,
            "period": "current_snapshot",
            "record": row,
        }
        for row in rows
        if row.get("avg_price_per_m2") is not None
    ]
