from __future__ import annotations

from typing import Literal

Source = Literal["sale", "rent"]


def normalize_listing_detail(raw: dict, source: Source) -> dict:
    """Set listing_type and price_unit on a raw listing detail dict.

    Pure normalizer shared between sale and rent crawlers. Inspects ``source``
    and the ``price_text`` content (presence of "/tháng" / "/thang") to decide
    whether the listing is a rent or sale. Does not touch any other field.
    """
    detail = dict(raw)
    price_text = (detail.get("price_text") or "").lower()

    if source == "rent" or "/tháng" in price_text or "/thang" in price_text:
        detail["listing_type"] = "rent"
        detail["price_unit"] = "million/month"
    else:
        detail["listing_type"] = "sale"
        detail["price_unit"] = "billion"

    return detail
