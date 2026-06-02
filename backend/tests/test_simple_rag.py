import pytest

from app.services.rag.ingest import build_listing_document, hf_row_to_listing_data
from app.services.rag.simple_rag import build_fallback_answer, extract_search_filters, format_listing_source
from scripts.load_hf_real_estates import _chunk_rows_for_insert, _validate_embedding_mode, parse_args


def test_hf_row_maps_to_listing_fields():
    row = {
        "name": "Ban can ho 2PN tai Quan 7",
        "description": "Can ho view song, noi that co ban.",
        "property_type_name": "Can ho chung cu",
        "province_name": "TP Ho Chi Minh",
        "district_name": "Quan 7",
        "ward_name": "Phuong Tan Phong",
        "street_name": "Nguyen Van Linh",
        "project_name": "Sunrise City",
        "price": 5200000000,
        "area": 72.5,
        "floor_count": 4,
        "frontage_width": 6.5,
        "road_width": 12,
        "bedroom_count": 2,
        "bathroom_count": 2,
        "house_direction": "Dong Nam",
        "published_at": "2026-01-02",
    }

    data = hf_row_to_listing_data(row, row_index=42)

    assert data["product_id"] == "hf-42"
    assert data["title"] == "Ban can ho 2PN tai Quan 7"
    assert data["price"] == 5.2
    assert data["price_text"] == "5.2 tỷ"
    assert data["price_per_m2"] == 71.72
    assert data["price_per_m2_text"] == "71.72 triệu/m²"
    assert data["area"] == 72.5
    assert data["area_text"] == "72.5 m²"
    assert data["bedrooms"] == 2
    assert data["bathrooms"] == 2
    assert data["floors"] == 4
    assert data["frontage"] == "6.5 m"
    assert data["road_width"] == "12 m"
    assert data["city"] == "TP Ho Chi Minh"
    assert data["district"] == "Quan 7"
    assert data["ward"] == "Phuong Tan Phong"
    assert data["address"] == "Sunrise City, Nguyen Van Linh, Phuong Tan Phong, Quan 7, TP Ho Chi Minh"
    assert data["listing_type"] == "sale"


def test_hf_loader_defaults_to_web_listing_import_without_embeddings():
    args = parse_args([])

    assert args.limit == 200_000
    assert args.all is False
    assert args.batch_size == 1_000
    assert args.with_embeddings is False


def test_hf_loader_accepts_full_dataset_flags():
    limit_zero = parse_args(["--limit", "0"])
    explicit_all = parse_args(["--all"])

    assert limit_zero.limit == 0
    assert limit_zero.all is False
    assert explicit_all.all is True


def test_hf_loader_rejects_legacy_listing_embedding_mode():
    with pytest.raises(RuntimeError, match="Listing.embedding da bi loai bo"):
        _validate_embedding_mode(True)


def test_hf_loader_splits_batches_under_asyncpg_parameter_limit():
    rows = [{f"field_{index}": index for index in range(34)} for _ in range(1_000)]

    chunks = list(_chunk_rows_for_insert(rows))

    assert [len(chunk) for chunk in chunks] == [963, 37]


def test_build_listing_document_includes_searchable_context():
    data = {
        "title": "Ban nha rieng",
        "description": "Gan truong hoc",
        "property_type": "Nha rieng",
        "city": "Ha Noi",
        "district": "Cau Giay",
        "ward": "Dich Vong",
        "price_text": "8 ty",
        "area_text": "60 m2",
        "bedrooms": 4,
        "bathrooms": 3,
    }

    document = build_listing_document(data)

    assert "Ban nha rieng" in document
    assert "Gan truong hoc" in document
    assert "Nha rieng" in document
    assert "Dich Vong, Cau Giay, Ha Noi" in document
    assert "8 ty" in document
    assert "60 m2" in document
    assert "4 phòng ngủ" in document


def test_extract_search_filters_from_vietnamese_query():
    filters = extract_search_filters("Tim can ho 2 phong ngu o Quan 7 TP Ho Chi Minh duoi 5 ty dien tich tu 60m2")

    assert filters["property_type"] == "Can ho"
    assert filters["city"] == "Ho Chi Minh"
    assert filters["district"] == "Quan 7"
    assert filters["bedrooms"] == 2
    assert filters["max_price"] == 5
    assert filters["min_area"] == 60
    assert filters["listing_type"] == "sale"


def test_format_listing_source_keeps_public_metadata_only():
    class ListingStub:
        id = 7
        product_id = "hf-7"
        title = "Can ho Quan 7"
        district = "Quan 7"
        city = "Ho Chi Minh"
        price_text = "4.8 ty"
        area_text = "70 m2"
        post_date = "2026-01-02"

    source = format_listing_source(ListingStub(), score=0.12345)

    assert source == {
        "id": 7,
        "product_id": "hf-7",
        "title": "Can ho Quan 7",
        "location": "Quan 7, Ho Chi Minh",
        "price_text": "4.8 ty",
        "area_text": "70 m2",
        "published_at": "2026-01-02",
        "score": 0.1235,
    }


def test_build_fallback_answer_uses_retrieved_listings():
    class ListingStub:
        title = "Nha Bac Tu Liem"
        district = "Bac Tu Liem"
        city = "Ha Noi"
        price_text = "7.45 ty"
        area_text = "37 m2"

    answer = build_fallback_answer("Tim nha o Ha Noi", [ListingStub()])

    assert "Tim thay 1 tin bat dong san" in answer
    assert "Nha Bac Tu Liem" in answer
    assert "Bac Tu Liem, Ha Noi" in answer
    assert "7.45 ty" in answer
    assert "37 m2" in answer
