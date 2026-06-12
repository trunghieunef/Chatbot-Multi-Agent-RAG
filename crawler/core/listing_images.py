"""Helpers for extracting listing image URLs from detail pages."""

from __future__ import annotations

import json
from urllib.parse import urljoin


IMAGE_ATTRS = ("src", "data-src", "data-original", "data-lazy", "lazy-src")


def normalize_image_url(value: str | None, base_url: str) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw or raw.startswith("data:") or raw.startswith("blob:"):
        return None
    return urljoin(base_url, raw)


def image_urls_from_page(page, base_url: str) -> list[str]:
    all_urls: list[str] = []
    gallery_urls: list[str] = []
    seen: set[str] = set()
    for image in page.query_selector_all("img"):
        url = None
        for attr in IMAGE_ATTRS:
            url = normalize_image_url(image.get_attribute(attr), base_url)
            if url:
                break
        if not url or url in seen:
            continue
        seen.add(url)
        all_urls.append(url)
        if "/resize/1275x717/" in url:
            gallery_urls.append(url)
    if gallery_urls:
        return gallery_urls
    return [
        url
        for url in all_urls
        if "staticfile.batdongsan.com.vn" not in url
        and "/images/" not in url
        and not url.lower().endswith(".svg")
    ]


def image_urls_json_from_page(page, base_url: str) -> str:
    return json.dumps(image_urls_from_page(page, base_url), ensure_ascii=False)
