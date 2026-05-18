from app.services.rag.ingest import build_listing_document, hf_row_to_listing_data
from app.services.rag.simple_rag import GeminiClient, extract_search_filters, format_listing_source
from app.services.rag.simple_rag import build_fallback_answer
from app.services.rag.simple_rag import run_simple_rag
from scripts.load_hf_real_estates import _chunk_rows_for_insert, parse_args


def test_hf_row_maps_to_listing_fields():
    row = {
        "name": "Bán căn hộ 2PN tại Quận 7",
        "description": "Căn hộ view sông, nội thất cơ bản.",
        "property_type_name": "Căn hộ chung cư",
        "province_name": "TP Hồ Chí Minh",
        "district_name": "Quận 7",
        "ward_name": "Phường Tân Phong",
        "street_name": "Nguyễn Văn Linh",
        "project_name": "Sunrise City",
        "price": 5200000000,
        "area": 72.5,
        "floor_count": 4,
        "frontage_width": 6.5,
        "road_width": 12,
        "bedroom_count": 2,
        "bathroom_count": 2,
        "house_direction": "Đông Nam",
        "published_at": "2026-01-02",
    }

    data = hf_row_to_listing_data(row, row_index=42)

    assert data["product_id"] == "hf-42"
    assert data["title"] == "Bán căn hộ 2PN tại Quận 7"
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
    assert data["city"] == "TP Hồ Chí Minh"
    assert data["district"] == "Quận 7"
    assert data["ward"] == "Phường Tân Phong"
    assert data["address"] == "Sunrise City, Nguyễn Văn Linh, Phường Tân Phong, Quận 7, TP Hồ Chí Minh"
    assert data["listing_type"] == "sale"


def test_hf_loader_defaults_to_web_listing_import_without_embeddings():
    args = parse_args([])

    assert args.limit == 200_000
    assert args.batch_size == 1_000
    assert args.with_embeddings is False


def test_hf_loader_splits_batches_under_asyncpg_parameter_limit():
    rows = [{f"field_{index}": index for index in range(34)} for _ in range(1_000)]

    chunks = list(_chunk_rows_for_insert(rows))

    assert [len(chunk) for chunk in chunks] == [963, 37]


def test_build_listing_document_includes_searchable_context():
    data = {
        "title": "Bán nhà riêng",
        "description": "Gần trường học",
        "property_type": "Nhà riêng",
        "city": "Hà Nội",
        "district": "Cầu Giấy",
        "ward": "Dịch Vọng",
        "price_text": "8 tỷ",
        "area_text": "60 m²",
        "bedrooms": 4,
        "bathrooms": 3,
    }

    document = build_listing_document(data)

    assert "Bán nhà riêng" in document
    assert "Gần trường học" in document
    assert "Nhà riêng" in document
    assert "Dịch Vọng, Cầu Giấy, Hà Nội" in document
    assert "8 tỷ" in document
    assert "60 m²" in document
    assert "4 phòng ngủ" in document


def test_extract_search_filters_from_vietnamese_query():
    filters = extract_search_filters("Tìm căn hộ 2 phòng ngủ ở Quận 7 TP Hồ Chí Minh dưới 5 tỷ diện tích từ 60m2")

    assert filters["property_type"] == "Căn hộ"
    assert filters["city"] == "Hồ Chí Minh"
    assert filters["district"] == "Quận 7"
    assert filters["bedrooms"] == 2
    assert filters["max_price"] == 5
    assert filters["min_area"] == 60
    assert filters["listing_type"] == "sale"


def test_format_listing_source_keeps_public_metadata_only():
    class ListingStub:
        id = 7
        product_id = "hf-7"
        title = "Căn hộ Quận 7"
        district = "Quận 7"
        city = "Hồ Chí Minh"
        price_text = "4.8 tỷ"
        area_text = "70 m²"
        post_date = "2026-01-02"

    source = format_listing_source(ListingStub(), score=0.12345)

    assert source == {
        "id": 7,
        "product_id": "hf-7",
        "title": "Căn hộ Quận 7",
        "location": "Quận 7, Hồ Chí Minh",
        "price_text": "4.8 tỷ",
        "area_text": "70 m²",
        "published_at": "2026-01-02",
        "score": 0.1235,
    }


def test_gemini_embed_keeps_client_alive_during_request():
    class FakeEmbedding:
        values = [0.1, 0.2, 0.3]

    class FakeResponse:
        embeddings = [FakeEmbedding()]

    class FakeModels:
        closed = False
        config = None

        def embed_content(self, model, contents, config=None):
            if self.closed:
                raise RuntimeError("client closed")
            self.config = config
            return FakeResponse()

    class FakeClient:
        def __init__(self, models):
            self.models = models

        def __del__(self):
            self.models.closed = True

    models = FakeModels()
    client = GeminiClient(api_key="test-key", model="test-model", embedding_model="test-embedding")
    client._client = lambda: FakeClient(models)

    assert client._embed_text_sync("hello") == [0.1, 0.2, 0.3]
    assert models.config.output_dimensionality == 768


def test_run_simple_rag_returns_public_contract(monkeypatch):
    class ListingStub:
        id = 7
        product_id = "hf-7"
        title = "Can ho Quan 7"
        district = "Quan 7"
        city = "Ho Chi Minh"
        price_text = "4.8 ty"
        area_text = "70 m2"
        post_date = "2026-01-02"

    async def fake_embed_text(self, text):
        assert text == "Tim can ho Quan 7"
        return [0.1, 0.2, 0.3]

    async def fake_generate_answer(self, query, listings):
        assert query == "Tim can ho Quan 7"
        assert listings[0].product_id == "hf-7"
        return "Co 1 can ho phu hop."

    async def fake_retrieve_listings(db, query_embedding, filters, top_k):
        assert query_embedding == [0.1, 0.2, 0.3]
        assert top_k == 5
        return [(ListingStub(), 0.12345)]

    monkeypatch.setattr(GeminiClient, "embed_text", fake_embed_text)
    monkeypatch.setattr(GeminiClient, "generate_answer", fake_generate_answer)

    import app.services.rag.simple_rag as simple_rag

    monkeypatch.setattr(simple_rag, "_retrieve_listings", fake_retrieve_listings)

    import asyncio

    result = asyncio.run(run_simple_rag("Tim can ho Quan 7", db=object()))

    assert result["final_response"] == "Co 1 can ho phu hop."
    assert result["agent_used"] == "simple_rag"
    assert result["suggested_actions"]
    assert result["sources"] == [
        {
            "id": 7,
            "product_id": "hf-7",
            "title": "Can ho Quan 7",
            "location": "Quan 7, Ho Chi Minh",
            "price_text": "4.8 ty",
            "area_text": "70 m2",
            "published_at": "2026-01-02",
            "score": 0.1235,
        }
    ]


def test_build_fallback_answer_uses_retrieved_listings():
    class ListingStub:
        title = "Nhà Bắc Từ Liêm"
        district = "Bắc Từ Liêm"
        city = "Hà Nội"
        price_text = "7.45 tỷ"
        area_text = "37 m²"

    answer = build_fallback_answer("Tìm nhà ở Hà Nội", [ListingStub()])

    assert "Tìm thấy 1 tin bất động sản" in answer
    assert "Nhà Bắc Từ Liêm" in answer
    assert "Bắc Từ Liêm, Hà Nội" in answer
    assert "7.45 tỷ" in answer
    assert "37 m²" in answer
