from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
CSV_CANDIDATES = [
    BASE_DIR / "apartments.csv",
    BASE_DIR / "batdongsancom-crawler" / "apartments.csv",
    BASE_DIR / "batdongsancom-crawler" / "apartments_cleaned.csv",
]

FALLBACK_LISTINGS: list[dict[str, Any]] = [
    {
        "product_id": "demo-1",
        "badge": "VIP Nổi bật",
        "title": "Căn hộ 2PN Vinhomes Grand Park, full nội thất, view thoáng công viên",
        "price_text": "4,68 tỷ",
        "area_text": "71 m²",
        "price_per_m2_text": "65,92 tr/m²",
        "bedrooms": "2",
        "bathrooms": "2",
        "location": "TP. Thủ Đức, Hồ Chí Minh",
        "description": "Thiết kế vuông vức, ban công rộng, phù hợp gia đình trẻ cần ở ngay.",
        "post_date": "Đăng hôm nay",
        "contact_name": "Nguyễn Minh Anh",
        "url": "#",
        "page_num": 1,
        "category": "Căn hộ chung cư",
    },
    {
        "product_id": "demo-2",
        "badge": "Đã xác thực",
        "title": "Nhà phố compound cao cấp, 5 tầng, gara ô tô, gần Phú Mỹ Hưng",
        "price_text": "18,9 tỷ",
        "area_text": "96 m²",
        "price_per_m2_text": "196,88 tr/m²",
        "bedrooms": "5",
        "bathrooms": "6",
        "location": "Quận 7, Hồ Chí Minh",
        "description": "Khu dân cư bảo vệ 24/7, pháp lý sạch, phù hợp ở và làm văn phòng.",
        "post_date": "Đăng 1 ngày trước",
        "contact_name": "Lê Quốc Duy",
        "url": "#",
        "page_num": 1,
        "category": "Nhà riêng",
    },
    {
        "product_id": "demo-3",
        "badge": "Giá tốt",
        "title": "Căn hộ studio cho thuê dài hạn gần biển Mỹ Khê, nội thất tối giản",
        "price_text": "12,5 triệu/tháng",
        "area_text": "38 m²",
        "price_per_m2_text": "329 nghìn/m²",
        "bedrooms": "1",
        "bathrooms": "1",
        "location": "Sơn Trà, Đà Nẵng",
        "description": "Không gian sáng, cửa kính lớn, phù hợp chuyên gia và người trẻ.",
        "post_date": "Đăng 2 ngày trước",
        "contact_name": "Hoàng Trâm",
        "url": "#",
        "page_num": 1,
        "category": "Cho thuê căn hộ",
    },
    {
        "product_id": "demo-4",
        "badge": "Mới cập nhật",
        "title": "Đất nền mặt tiền đường lớn, gần khu công nghiệp VSIP, sổ riêng",
        "price_text": "2,35 tỷ",
        "area_text": "100 m²",
        "price_per_m2_text": "23,5 tr/m²",
        "bedrooms": "",
        "bathrooms": "",
        "location": "Thuận An, Bình Dương",
        "description": "Phù hợp đầu tư dài hạn, hạ tầng hoàn thiện, khu dân cư hiện hữu.",
        "post_date": "Đăng 3 ngày trước",
        "contact_name": "Trần Gia Huy",
        "url": "#",
        "page_num": 1,
        "category": "Đất nền",
    },
    {
        "product_id": "demo-5",
        "badge": "Dự án hot",
        "title": "Shophouse trung tâm hành chính mới, mặt tiền đại lộ, bàn giao ngay",
        "price_text": "12,8 tỷ",
        "area_text": "120 m²",
        "price_per_m2_text": "106,7 tr/m²",
        "bedrooms": "4",
        "bathrooms": "4",
        "location": "Biên Hòa, Đồng Nai",
        "description": "Sản phẩm hiếm ở trục thương mại chính, phù hợp khai thác cho thuê.",
        "post_date": "Đăng 4 ngày trước",
        "contact_name": "Phạm Khánh Linh",
        "url": "#",
        "page_num": 1,
        "category": "Nhà phố thương mại",
    },
    {
        "product_id": "demo-6",
        "badge": "Chính chủ",
        "title": "Căn hộ 3PN khu Tây Hồ, ban công hồ, full tiện ích, nhận nhà ngay",
        "price_text": "7,25 tỷ",
        "area_text": "110 m²",
        "price_per_m2_text": "65,9 tr/m²",
        "bedrooms": "3",
        "bathrooms": "2",
        "location": "Tây Hồ, Hà Nội",
        "description": "Căn góc, thiết kế thông thoáng, nội thất liền tường cao cấp.",
        "post_date": "Đăng hôm nay",
        "contact_name": "Đào Việt Sơn",
        "url": "#",
        "page_num": 1,
        "category": "Căn hộ chung cư",
    },
]

PRICE_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)", re.IGNORECASE)
AREA_NUMBER_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m", re.IGNORECASE)


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def parse_decimal(text: str) -> float | None:
    match = PRICE_NUMBER_RE.search(text or "")
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def parse_price_billion(text: str) -> float | None:
    value = parse_decimal(text)
    lowered = (text or "").lower()
    if value is None:
        return None
    if "tỷ" in lowered or "ty" in lowered:
        return value
    if "triệu" in lowered or lowered.endswith("tr"):
        return value / 1000
    if "nghìn" in lowered or "ngàn" in lowered:
        return value / 1_000_000
    return value


def parse_area_m2(text: str) -> float | None:
    match = AREA_NUMBER_RE.search(text or "")
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def derive_category(record: dict[str, Any]) -> str:
    title = normalize_text(record.get("title")).lower()
    if "đất" in title:
        return "Đất nền"
    if "shophouse" in title:
        return "Nhà phố thương mại"
    if "thuê" in title:
        return "Cho thuê căn hộ"
    if "nhà phố" in title or "nhà riêng" in title:
        return "Nhà riêng"
    return "Căn hộ chung cư"


def add_derived_fields(record: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(record)
    enriched["category"] = normalize_text(record.get("category")) or derive_category(record)
    enriched["badge"] = normalize_text(record.get("badge")) or "Tin nổi bật"
    enriched["price_billion"] = parse_price_billion(normalize_text(record.get("price_text")))
    enriched["area_m2"] = parse_area_m2(normalize_text(record.get("area_text")))
    return enriched


def load_csv_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as csv_file:
        return [add_derived_fields(row) for row in csv.DictReader(csv_file)]


def load_records() -> tuple[list[dict[str, Any]], str]:
    for path in CSV_CANDIDATES:
        if path.exists():
            return load_csv_records(path), str(path.relative_to(BASE_DIR))
    return [add_derived_fields(item) for item in FALLBACK_LISTINGS], "fallback-demo-data"


LISTINGS, DATA_SOURCE = load_records()


def listing_matches(
    listing: dict[str, Any],
    search: str | None,
    location: str | None,
    category: str | None,
    min_price: float | None,
    max_price: float | None,
) -> bool:
    if search:
        haystack = " ".join(
            [
                normalize_text(listing.get("title")),
                normalize_text(listing.get("location")),
                normalize_text(listing.get("description")),
            ]
        ).lower()
        if search.lower() not in haystack:
            return False

    if location and location.lower() not in normalize_text(listing.get("location")).lower():
        return False
    if category and category.lower() != normalize_text(listing.get("category")).lower():
        return False

    price_billion = listing.get("price_billion")
    if min_price is not None and (price_billion is None or price_billion < min_price):
        return False
    if max_price is not None and (price_billion is None or price_billion > max_price):
        return False
    return True


def build_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    price_values = [r["price_billion"] for r in records if isinstance(r.get("price_billion"), (int, float))]
    location_counter = Counter(normalize_text(r.get("location")) for r in records if normalize_text(r.get("location")))
    category_counter = Counter(normalize_text(r.get("category")) for r in records if normalize_text(r.get("category")))
    return {
        "total_listings": len(records),
        "total_locations": len(location_counter),
        "average_price_billion": round(sum(price_values) / len(price_values), 2) if price_values else None,
        "data_source": DATA_SOURCE,
        "top_locations": [{"name": name, "count": count} for name, count in location_counter.most_common(8)],
        "quick_links": [{"name": name, "count": count} for name, count in category_counter.most_common(8)],
    }


app = FastAPI(title="Real Estate Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/listings")
def get_listings(
    search: str | None = Query(default=None),
    location: str | None = Query(default=None),
    category: str | None = Query(default=None),
    min_price: float | None = Query(default=None, description="Billion VND"),
    max_price: float | None = Query(default=None, description="Billion VND"),
    limit: int = Query(default=12, ge=1, le=100),
) -> dict[str, Any]:
    filtered = [
        item
        for item in LISTINGS
        if listing_matches(item, search, location, category, min_price, max_price)
    ]
    return {"items": filtered[:limit], "total": len(filtered), "limit": limit}


@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    return build_stats(LISTINGS)


@app.get("/api/categories")
def get_categories() -> dict[str, list[str]]:
    categories = sorted({normalize_text(item.get("category")) for item in LISTINGS if normalize_text(item.get("category"))})
    return {"items": categories}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
