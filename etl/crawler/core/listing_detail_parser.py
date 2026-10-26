from __future__ import annotations

from typing import Literal

Source = Literal["sale", "rent"]


def _label_key(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def is_shell_listing_page(title_text: str, page_title: str = "") -> bool:
    """Return True for anti-bot/shell pages that are not listing details."""
    combined = _label_key(f"{title_text} {page_title}")
    title_key = _label_key(title_text)
    return (
        not title_key
        or title_key in {"batdongsan.com.vn", "batdongsan", "propertyguru"}
        or "just a moment" in combined
        or "access denied" in combined
        or "vui long cho" in combined
    )


def _element_text(element) -> str:
    if element is None:
        return ""
    try:
        return element.inner_text().strip()
    except Exception:
        return ""


def _compact_text(value: str) -> str:
    return " ".join((value or "").split())


def _first_address_line(value: str) -> str:
    lines = [line.strip() for line in (value or "").splitlines() if line.strip()]
    if lines:
        return _compact_text(lines[0])
    text = _compact_text(value)
    if text.endswith(")") and " (" in text:
        return text.rsplit(" (", 1)[0].strip()
    return text


def extract_listing_address_from_page(page) -> str:
    """Extract the real listing address, falling back to breadcrumbs.

    Batdongsan detail pages expose the specific address in
    ``.re__ldp-address``. Breadcrumbs are category/location navigation and can
    look address-like, so they are intentionally used last.
    """
    line_1 = _first_address_line(
        _element_text(page.query_selector(".re__ldp-address .re__address-line-1"))
    )
    if line_1:
        return line_1

    address_container = _first_address_line(
        _element_text(page.query_selector(".re__ldp-address .re__address"))
    )
    if address_container:
        return address_container

    for selector in (".re__pr-short-description--address", ".js__pr-address"):
        address = _compact_text(_element_text(page.query_selector(selector)))
        if address:
            return address

    breadcrumb = page.query_selector(".re__breadcrumb")
    if not breadcrumb:
        return ""

    crumbs = breadcrumb.query_selector_all("a")
    if crumbs:
        parts = [_compact_text(_element_text(crumb)) for crumb in crumbs]
        return ", ".join(part for part in parts if part)

    return _compact_text(_element_text(breadcrumb).replace("\n", ", "))


def extract_listing_property_type_from_page(page) -> str:
    """Use the breadcrumb category as property_type fallback."""
    breadcrumb = page.query_selector(".re__breadcrumb")
    if not breadcrumb:
        return ""

    crumbs = breadcrumb.query_selector_all("a")
    if crumbs:
        parts = [_compact_text(_element_text(crumb)) for crumb in crumbs]
        parts = [part for part in parts if part]
        return parts[-1] if len(parts) >= 4 else ""

    text = _compact_text(_element_text(breadcrumb))
    separator = "/" if "/" in text else ","
    parts = [part.strip() for part in text.split(separator) if part.strip()]
    return parts[-1] if len(parts) >= 4 else ""


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
