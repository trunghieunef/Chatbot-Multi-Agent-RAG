# M2 Multi-Source Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the M1 sale-only foundation to ingest three new sources — rent listings, real-estate projects, and news/articles — by reusing the M1 crawler core, cleaning, chunking, embedding, and hybrid retrieval, plus adding a geocoding/intent enrichment layer that fills `latitude`/`longitude` and richer intent tags.

**Architecture:** Keep PostgreSQL + pgvector as single source of truth. Add `crawler/rent`, `crawler/projects`, `crawler/news` packages on top of `crawler/core/`; add `data_pipeline/enrich.py` (geocoding + LLM intent extraction); add `projects_ingestor.py` and `news_ingestor.py`; extend hybrid search to support `parent_type="project"` and `parent_type="article"`; wire Market Analysis Agent (SQL aggregates) and rent results through Property Search Agent.

**Tech Stack:** Python 3.11, Playwright + stealth (already in `crawler/core/`), Google Gemini 2.0 Flash for intent extraction, Nominatim (free) or Goong (paid) for geocoding, SQLAlchemy async, Alembic.

---

## Scope And Existing Repo Notes

- M2 assumes M1 is merged: `crawler/core/`, `data_pipeline/clean.py|chunk.py|embed.py`, `data_pipeline/ingestors/listings_ingestor.py`, `chatbot/tools/hybrid_search.py`, `Article` and `Chunk` ORM models, and Alembic migration `20260525_0001` are all in place.
- Rent crawl reuses `crawler/sale/crawl_details.py` parsers because batdongsan.com structures rent and sale detail pages identically; only the listing-list root URL and the price unit normalization differ.
- Project pages have a different DOM. M2 ships a project-specific selector set, not a fork of the listing parser.
- News pages are HTML articles with title/body/category. M2 only ingests `category="news"`. Legal PDFs (`category="legal"`) are M4.
- `data_pipeline/enrich.py` is introduced now. Geocoding defaults to Nominatim with an explicit `User-Agent` and 1-second per-request rate limit; the user can flip to Goong via env vars without code changes.
- Intent tag extraction in M1 is rule-based inside `chunk.py`. M2 adds an optional LLM-based extractor in `enrich.py` that runs once per listing and stores the tag string; `chunk.py` still consumes the tags but no longer recomputes them when the enriched value is present.
- Hybrid search currently resolves only listings. M2 adds `resolve_to_project_records` and `resolve_to_article_records` and a `parent_type` switch.
- Market Analysis Agent in `chatbot/agents/market_analysis.py` is a placeholder. M2 wires it to a small SQL aggregation tool (`chatbot/tools/market_stats.py`) — no vector retrieval, just aggregates over `listings` and `projects`.
- Property Search Agent already calls `hybrid_search(parent_type="listing")` from M1. In M2 it gains a `listing_type` filter pass-through so users can ask for rentals.

## File Structure

- Create: `crawler/rent/__init__.py`, `crawler/rent/crawl_urls.py`, `crawler/rent/crawl_details.py`
  Rent URL list crawler (root `/nha-dat-cho-thue`) and detail crawler (reuses sale parser via shared helper).
- Modify: `crawler/sale/crawl_details.py`
  Extract the listing detail parser into a shared callable so rent can import it without duplicating selectors.
- Create: `crawler/core/listing_detail_parser.py`
  Holds the shared selector logic so sale and rent both import from one place.
- Create: `crawler/projects/__init__.py`, `crawler/projects/crawl_urls.py`, `crawler/projects/crawl_details.py`
  Project URL list crawler and project detail parser.
- Create: `crawler/news/__init__.py`, `crawler/news/crawl_articles.py`
  News article URL+content crawler (single pass).
- Create: `data_pipeline/enrich.py`
  Geocoder client (Nominatim/Goong) and Gemini-based intent tag extractor with deterministic caching.
- Modify: `data_pipeline/chunk.py`
  Accept pre-computed `intent_tags` from enrichment instead of recomputing.
- Modify: `data_pipeline/ingestors/listings_ingestor.py`
  Insert geocoding + intent extraction step between clean and chunk; persist `latitude`, `longitude`.
- Create: `data_pipeline/ingestors/projects_ingestor.py`
  CLI orchestration for projects: clean -> upsert project -> embed chunks -> insert chunks.
- Create: `data_pipeline/ingestors/news_ingestor.py`
  CLI orchestration for news: clean -> upsert article -> embed chunks -> insert chunks.
- Modify: `data_pipeline/clean.py`
  Add `row_to_project` and `row_to_article` normalizers; keep `row_to_listing` unchanged.
- Modify: `chatbot/tools/hybrid_search.py`
  Add `resolve_to_project_records`, `resolve_to_article_records`, and parent-type dispatch.
- Create: `chatbot/tools/market_stats.py`
  SQL aggregate helpers used by Market Analysis Agent.
- Modify: `chatbot/agents/market_analysis.py`
  Call `market_stats` and format results.
- Modify: `chatbot/agents/property_search.py`
  Forward `listing_type` filter so rent queries route correctly.
- Create: `backend/alembic/versions/20260601_0002_m2_geocode_indexes.py`
  Index `(latitude, longitude)`, partial index on `listing_type` and rent-only filtering, and a unique slug for projects if missing.
- Create tests under `backend/tests/` for enrich, projects ingestor, news ingestor, market_stats, and hybrid search project/article paths.

---

### Task 1: Configuration For Geocoding And Intent Extraction

**Files:**
- Modify: `backend/app/config.py`
- Modify: `chatbot/config.py`
- Test: `backend/tests/test_m2_config.py`

- [ ] **Step 1: Write failing config test**

Create `backend/tests/test_m2_config.py`:

```python
from app.config import Settings


def test_m2_settings_defaults():
    settings = Settings()

    assert settings.GEOCODER_PROVIDER == "nominatim"
    assert settings.GEOCODER_USER_AGENT.startswith("realestate-chatbot")
    assert settings.GEOCODER_RATE_LIMIT_SECONDS == 1.0
    assert settings.GOONG_API_KEY == ""
    assert settings.INTENT_EXTRACTOR == "rule"
    assert settings.GEMINI_INTENT_MODEL == "gemini-2.0-flash"
```

- [ ] **Step 2: Run the test and confirm it fails**

```powershell
cd backend
python -m pytest tests/test_m2_config.py -q
```

Expected: fail because the new fields are missing.

- [ ] **Step 3: Add config fields**

Append to `Settings` in `backend/app/config.py`:

```python
    # Geocoding
    GEOCODER_PROVIDER: str = "nominatim"          # 'nominatim' | 'goong'
    GEOCODER_USER_AGENT: str = "realestate-chatbot/0.1 (contact@example.com)"
    GEOCODER_RATE_LIMIT_SECONDS: float = 1.0
    GOONG_API_KEY: str = ""

    # Intent extraction
    INTENT_EXTRACTOR: str = "rule"                # 'rule' | 'gemini'
    GEMINI_INTENT_MODEL: str = "gemini-2.0-flash"
```

Mirror the same constants in `chatbot/config.py`:

```python
GEOCODER_PROVIDER = os.getenv("GEOCODER_PROVIDER", "nominatim")
GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "realestate-chatbot/0.1 (contact@example.com)")
GEOCODER_RATE_LIMIT_SECONDS = float(os.getenv("GEOCODER_RATE_LIMIT_SECONDS", "1.0"))
GOONG_API_KEY = os.getenv("GOONG_API_KEY", "")

INTENT_EXTRACTOR = os.getenv("INTENT_EXTRACTOR", "rule")
GEMINI_INTENT_MODEL = os.getenv("GEMINI_INTENT_MODEL", "gemini-2.0-flash")
```

- [ ] **Step 4: Run config test**

```powershell
cd backend
python -m pytest tests/test_m2_config.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/config.py chatbot/config.py backend/tests/test_m2_config.py
git commit -m "configure m2 geocoding and intent extraction"
```

---

### Task 2: Extract Shared Listing Detail Parser

**Files:**
- Create: `crawler/core/listing_detail_parser.py`
- Modify: `crawler/sale/crawl_details.py`
- Test: `backend/tests/test_listing_detail_parser.py`

- [ ] **Step 1: Write parser test using a stub Playwright element**

Create `backend/tests/test_listing_detail_parser.py`:

```python
from crawler.core.listing_detail_parser import normalize_listing_detail


def test_normalize_listing_detail_marks_rent_when_price_per_month():
    raw = {
        "product_id": "p1",
        "title": "Cho thuê căn hộ 2PN",
        "price_text": "15 triệu/tháng",
        "area_text": "75 m²",
        "address": "Phường 1, Quận 7, Hồ Chí Minh",
        "url": "https://batdongsan.com.vn/cho-thue/abc",
    }

    detail = normalize_listing_detail(raw, source="rent")

    assert detail["listing_type"] == "rent"
    assert detail["price_unit"] == "million/month"


def test_normalize_listing_detail_marks_sale_for_sale_source():
    raw = {
        "product_id": "p2",
        "title": "Bán nhà phố",
        "price_text": "6,2 tỷ",
        "url": "https://batdongsan.com.vn/ban/xyz",
    }

    detail = normalize_listing_detail(raw, source="sale")

    assert detail["listing_type"] == "sale"
    assert detail["price_unit"] == "billion"
```

- [ ] **Step 2: Run the test and confirm import failure**

```powershell
cd backend
python -m pytest tests/test_listing_detail_parser.py -q
```

Expected: fail because `crawler.core.listing_detail_parser` does not exist.

- []**Step 3: Create the parser module**

Create `crawler/core/listing_detail_parser.py`:

```python
from __future__ import annotations

from typing import Literal

Source = Literal["sale", "rent"]


def normalize_listing_detail(raw: dict, source: Source) -> dict:
    detail = dict(raw)
    price_text = (detail.get("price_text") or "").lower()

    if source == "rent" or "/tháng" in price_text or "/thang" in price_text:
        detail["listing_type"] = "rent"
        detail["price_unit"] = "million/month"
    else:
        detail["listing_type"] = "sale"
        detail["price_unit"] = "billion"

    return detail
```

- [ ] **Step 4: Migrate sale crawler to use shared parser**

In `crawler/sale/crawl_details.py`, after building each detail row, call:

```python
from crawler.core.listing_detail_parser import normalize_listing_detail

detail = normalize_listing_detail(detail, source="sale")
```

Do not change selector logic; just route the final dict through `normalize_listing_detail`.

- [ ] **Step 5: Run parser test**

```powershell
cd backend
python -m pytest tests/test_listing_detail_parser.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add crawler/core/listing_detail_parser.py crawler/sale/crawl_details.py backend/tests/test_listing_detail_parser.py
git commit -m "share listing detail normalization between sale and rent"
```

---

### Task 3: Rent Crawler Package

**Files:**
- Create: `crawler/rent/__init__.py`
- Create: `crawler/rent/crawl_urls.py`
- Create: `crawler/rent/crawl_details.py`

- [ ] **Step 1: Copy and adapt URL crawler**

Create `crawler/rent/crawl_urls.py` based on `crawler/sale/crawl_urls.py` with only the BASE_URL changed:

```python
BASE_URL = "https://batdongsan.com.vn/nha-dat-cho-thue"
```

Reuse `crawler.core.csv_writer` and the same `argparse` flags (`--pages`, `--output`, `--workers`, `--since`).

- [ ] **Step 2: Copy and adapt detail crawler**

Create `crawler/rent/crawl_details.py` based on `crawler/sale/crawl_details.py`. After parsing each detail row call:

```python
from crawler.core.listing_detail_parser import normalize_listing_detail

detail = normalize_listing_detail(detail, source="rent")
```

Keep the input CSV default `data/raw/rent_urls.csv` and output default `data/raw/rent_details.csv`.

- [ ] **Step 3: Compile crawler package**

```powershell
python -m compileall crawler
```

Expected: all files compile.

- [ ] **Step 4: Manual smoke test**

Run a 1-page sweep:

```powershell
python -m crawler.rent.crawl_urls --pages 1 1 --output data\raw\rent_urls_test.csv
```

Expected: CSV contains rent listing URLs and `product_id`s. Skip if batdongsan.com is rate-limiting; record the timestamp and rerun.

- [ ] **Step 5: Commit**

```powershell
git add crawler/rent
git commit -m "add rent crawler package"
```

---

### Task 4: Geocoding Client

**Files:**
- Create: `data_pipeline/enrich.py`
- Test: `backend/tests/test_enrich_geocode.py`

- [ ] **Step 1: Write failing geocoder tests with a fake HTTP client**

Create `backend/tests/test_enrich_geocode.py`:

```python
import pytest

from data_pipeline.enrich import NominatimGeocoder


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        return FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_nominatim_returns_first_result_lat_lon():
    client = FakeClient([{"lat": "10.7", "lon": "106.7"}])
    geocoder = NominatimGeocoder(user_agent="test/0.1", rate_limit_seconds=0, client_factory=lambda: client)

    coord = await geocoder.geocode("Quận 7, Hồ Chí Minh")

    assert coord == (10.7, 106.7)
    assert client.calls[0][1]["q"] == "Quận 7, Hồ Chí Minh"
    assert client.calls[0][2]["User-Agent"] == "test/0.1"


@pytest.mark.asyncio
async def test_nominatim_returns_none_for_empty_response():
    geocoder = NominatimGeocoder(
        user_agent="test/0.1", rate_limit_seconds=0, client_factory=lambda: FakeClient([])
    )

    assert await geocoder.geocode("không tồn tại") is None


@pytest.mark.asyncio
async def test_nominatim_returns_none_for_blank_address():
    geocoder = NominatimGeocoder(user_agent="test/0.1", rate_limit_seconds=0, client_factory=lambda: FakeClient([]))

    assert await geocoder.geocode("") is None
```

- [ ] **Step 2: Run the tests and confirm import failure**

```powershell
cd backend
python -m pytest tests/test_enrich_geocode.py -q
```

Expected: fail because `data_pipeline.enrich` does not exist.

- []**Step 3: Implement the geocoder**

Create `data_pipeline/enrich.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

import httpx


@dataclass
class NominatimGeocoder:
    user_agent: str
    rate_limit_seconds: float = 1.0
    base_url: str = "https://nominatim.openstreetmap.org/search"
    client_factory: Callable[[], object] = field(default=lambda: httpx.AsyncClient(timeout=15))

    async def geocode(self, address: str) -> tuple[float, float] | None:
        if not address or not address.strip():
            return None

        async with self.client_factory() as client:
            response = await client.get(
                self.base_url,
                params={"q": address.strip(), "format": "json", "limit": 1},
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            data = response.json()

        if self.rate_limit_seconds > 0:
            await asyncio.sleep(self.rate_limit_seconds)

        if not data:
            return None

        try:
            return float(data[0]["lat"]), float(data[0]["lon"])
        except (KeyError, ValueError):
            return None
```

- [ ] **Step 4: Run geocoder tests**

```powershell
cd backend
python -m pytest tests/test_enrich_geocode.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/enrich.py backend/tests/test_enrich_geocode.py
git commit -m "add nominatim geocoder"
```

---

### Task 5: LLM Intent Tag Extractor

**Files:**
- Modify: `data_pipeline/enrich.py`
- Modify: `data_pipeline/chunk.py`
- Test: `backend/tests/test_enrich_intent.py`
- Test: `backend/tests/test_chunk_uses_precomputed_tags.py`

- [ ] **Step 1: Write failing intent extractor tests**

Create `backend/tests/test_enrich_intent.py`:

```python
import pytest

from data_pipeline.enrich import GeminiIntentExtractor


class FakeResp:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append((model, contents))
        return FakeResp(self.payload)


class FakeClient:
    def __init__(self, payload):
        self.models = FakeModels(payload)


@pytest.mark.asyncio
async def test_gemini_intent_extractor_parses_json_array():
    client = FakeClient('{"tags": ["gần trường", "view sông"]}')
    extractor = GeminiIntentExtractor(api_key="k", client=client, model="gemini-2.0-flash")

    tags = await extractor.extract("Căn hộ gần trường, view sông đẹp.")

    assert tags == ["gần trường", "view sông"]


@pytest.mark.asyncio
async def test_gemini_intent_extractor_returns_empty_on_invalid_json():
    extractor = GeminiIntentExtractor(api_key="k", client=FakeClient("not json"))

    assert await extractor.extract("nội dung") == []


@pytest.mark.asyncio
async def test_gemini_intent_extractor_returns_empty_for_blank_input():
    extractor = GeminiIntentExtractor(api_key="k", client=FakeClient('{"tags": []}'))

    assert await extractor.extract("") == []
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
cd backend
python -m pytest tests/test_enrich_intent.py -q
```

Expected: fail because `GeminiIntentExtractor` is missing.

- [ ] **Step 3: Append the extractor to `data_pipeline/enrich.py`**

```python
import asyncio
import json
from dataclasses import dataclass


INTENT_PROMPT = (
    "Bạn là bộ trích xuất tag bất động sản. "
    "Đọc mô tả sau và trả JSON dạng {{\"tags\": [\"...\"]}} "
    "với tối đa 8 tag ngắn gọn, viết thường, không trùng lặp. "
    "Nội dung: {content}"
)


@dataclass
class GeminiIntentExtractor:
    api_key: str
    model: str = "gemini-2.0-flash"
    client: object | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            from google import genai

            if not self.api_key:
                raise ValueError("GEMINI_API_KEY required for intent extraction")
            self.client = genai.Client(api_key=self.api_key)

    async def extract(self, content: str) -> list[str]:
        if not content or not content.strip():
            return []
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model,
            contents=INTENT_PROMPT.format(content=content[:1500]),
        )
        try:
            payload = json.loads(response.text)
            tags = payload.get("tags", [])
            return [tag for tag in tags if isinstance(tag, str) and tag.strip()]
        except (json.JSONDecodeError, AttributeError, TypeError):
            return []
```

- [ ] **Step 4: Write failing test ensuring chunker accepts pre-computed tags**

Create `backend/tests/test_chunk_uses_precomputed_tags.py`:

```python
from data_pipeline.chunk import build_listing_chunks


def test_build_listing_chunks_uses_precomputed_intent_tags():
    listing = {
        "title": "Bán căn hộ 2PN",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4 tỷ",
        "area_text": "75 m²",
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "address": "Phường 1, Quận 7",
        "description": "Mô tả ngắn.",
        "intent_tags": ["view sông", "gần trường mới"],
    }

    chunks = build_listing_chunks(listing)
    by_type = {chunk["chunk_type"]: chunk for chunk in chunks}

    assert by_type["intent_tags"]["text"] == "Nhu cầu phù hợp: view sông, gần trường mới"


def test_build_listing_chunks_falls_back_to_rule_based_tags_when_missing():
    listing = {
        "title": "Bán căn hộ 2PN",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4 tỷ",
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "description": "Gần trường học, sổ hồng đầy đủ.",
    }

    chunks = build_listing_chunks(listing)
    by_type = {chunk["chunk_type"]: chunk for chunk in chunks}

    assert "gần trường" in by_type["intent_tags"]["text"]
    assert "pháp lý rõ" in by_type["intent_tags"]["text"]
```

- [ ] **Step 5: Run the new chunk test and confirm it fails**

```powershell
cd backend
python -m pytest tests/test_chunk_uses_precomputed_tags.py -q
```

Expected: fail because the current chunker recomputes tags and ignores `listing["intent_tags"]`.

- [ ] **Step 6: Update `data_pipeline/chunk.py`**

Inside `build_listing_chunks`, replace the tag computation with:

```python
precomputed = listing.get("intent_tags")
if isinstance(precomputed, list) and precomputed:
    tags = [str(tag) for tag in precomputed if str(tag).strip()]
else:
    tags = extract_intent_tags(" ".join([title, description, address, legal_status, furniture]))

if tags:
    chunks.append({"chunk_type": "intent_tags", "text": "Nhu cầu phù hợp: " + ", ".join(tags)})
```

- [ ] **Step 7: Run all chunk + intent tests**

```powershell
cd backend
python -m pytest tests/test_chunk.py tests/test_chunk_uses_precomputed_tags.py tests/test_enrich_intent.py -q
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add data_pipeline/enrich.py data_pipeline/chunk.py backend/tests/test_enrich_intent.py backend/tests/test_chunk_uses_precomputed_tags.py
git commit -m "add gemini intent extractor and precomputed tag chunking"
```

---

### Task 6: Listings Ingestor — Geocode + Intent Pass

**Files:**
- Modify: `data_pipeline/ingestors/listings_ingestor.py`
- Test: `backend/tests/test_listings_ingestor_enrichment.py`

- [] **Step 1: Write failing test for the enrichment hook**

Create `backend/tests/test_listings_ingestor_enrichment.py`:

```python
import pytest

from data_pipeline.ingestors.listings_ingestor import enrich_listing_data


class StubGeocoder:
    def __init__(self, coord):
        self.coord = coord
        self.calls = []

    async def geocode(self, address):
        self.calls.append(address)
        return self.coord


class StubIntent:
    def __init__(self, tags):
        self.tags = tags
        self.calls = []

    async def extract(self, content):
        self.calls.append(content)
        return list(self.tags)


@pytest.mark.asyncio
async def test_enrich_listing_data_fills_lat_lon_and_tags():
    listing = {
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "description": "Gần trường học, view sông",
    }
    geocoder = StubGeocoder((10.73, 106.72))
    intent = StubIntent(["gần trường", "view sông"])

    enriched = await enrich_listing_data(listing, geocoder=geocoder, intent_extractor=intent)

    assert enriched["latitude"] == 10.73
    assert enriched["longitude"] == 106.72
    assert enriched["intent_tags"] == ["gần trường", "view sông"]


@pytest.mark.asyncio
async def test_enrich_listing_data_skips_geocode_for_blank_address():
    listing = {"address": "", "description": "..."}
    geocoder = StubGeocoder(None)
    intent = StubIntent([])

    enriched = await enrich_listing_data(listing, geocoder=geocoder, intent_extractor=intent)

    assert enriched["latitude"] is None
    assert enriched["longitude"] is None
    assert geocoder.calls == []
```

- [ ] **Step 2: Run the test and confirm it fails**

```powershell
cd backend
python -m pytest tests/test_listings_ingestor_enrichment.py -q
```

Expected: fail because `enrich_listing_data` does not exist.

- [ ] **Step 3: Add `enrich_listing_data` to the ingestor**

Append to `data_pipeline/ingestors/listings_ingestor.py`:

```python
async def enrich_listing_data(listing: dict, *, geocoder, intent_extractor) -> dict:
    enriched = dict(listing)

    address = (enriched.get("address") or "").strip()
    if address:
        coord = await geocoder.geocode(address)
        if coord:
            enriched["latitude"], enriched["longitude"] = coord
        else:
            enriched.setdefault("latitude", None)
            enriched.setdefault("longitude", None)
    else:
        enriched.setdefault("latitude", None)
        enriched.setdefault("longitude", None)

    description_for_intent = " ".join(
        part
        for part in (enriched.get("title"), enriched.get("description"), enriched.get("address"))
        if part
    )
    enriched["intent_tags"] = await intent_extractor.extract(description_for_intent)
    return enriched
```

- [ ] **Step 4: Wire `ingest_listing_rows` to call enrichment**

In `ingest_listing_rows`, after `listing_data = row_to_listing(row)` and before `upsert_listing`, add:

```python
listing_data = await enrich_listing_data(
    listing_data,
    geocoder=geocoder,
    intent_extractor=intent_extractor,
)
```

Construct `geocoder` and `intent_extractor` once at the top of `ingest_listing_rows`:

```python
from data_pipeline.enrich import GeminiIntentExtractor, NominatimGeocoder

geocoder = NominatimGeocoder(
    user_agent=settings.GEOCODER_USER_AGENT,
    rate_limit_seconds=settings.GEOCODER_RATE_LIMIT_SECONDS,
)
if settings.INTENT_EXTRACTOR == "gemini" and settings.GEMINI_API_KEY:
    intent_extractor = GeminiIntentExtractor(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_INTENT_MODEL,
    )
else:
    class _NoOpIntent:
        async def extract(self, _content):
            return []
    intent_extractor = _NoOpIntent()
```

- [ ] **Step 5: Run ingestor enrichment test**

```powershell
cd backend
python -m pytest tests/test_listings_ingestor_enrichment.py tests/test_listings_ingestor.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add data_pipeline/ingestors/listings_ingestor.py backend/tests/test_listings_ingestor_enrichment.py
git commit -m "geocode and tag listings during ingestion"
```

---

### Task 7: Project Crawler And Ingestor

**Files:**
- Create: `crawler/projects/__init__.py`, `crawler/projects/crawl_urls.py`, `crawler/projects/crawl_details.py`
- Modify: `data_pipeline/clean.py`
- Create: `data_pipeline/ingestors/projects_ingestor.py`
- Test: `backend/tests/test_clean_project.py`, `backend/tests/test_projects_ingestor.py`

- [ ] **Step 1: Project URL crawler**

Create `crawler/projects/crawl_urls.py` modeled on `crawler/sale/crawl_urls.py` with `BASE_URL = "https://batdongsan.com.vn/du-an"` and CSV fields `["slug", "name", "url"]`.

- [ ] **Step 2: Project detail crawler**

Create `crawler/projects/crawl_details.py`. Output CSV columns:

```
slug, name, developer, location, district, city, total_units, price_range, area_range, status, project_type, description, amenities, url
```

`amenities` is a JSON-encoded list of strings.

- [ ] **Step 3: Write failing tests for `row_to_project`**

Create `backend/tests/test_clean_project.py`:

```python
from data_pipeline.clean import row_to_project


def test_row_to_project_normalizes_string_fields_and_amenities():
    row = {
        "slug": "vinhomes-grand-park",
        "name": "Vinhomes Grand Park",
        "developer": "Vinhomes",
        "location": "Quận 9, Hồ Chí Minh",
        "district": "Quận 9",
        "city": "Hồ Chí Minh",
        "total_units": "10000",
        "price_range": "2,5 - 4,8 tỷ",
        "area_range": "55 - 120 m²",
        "status": "selling",
        "project_type": "apartment",
        "description": "Khu đô thị lớn",
        "amenities": '["Hồ bơi", "Gym", "Công viên"]',
        "url": "https://batdongsan.com.vn/du-an/vinhomes-grand-park",
    }

    project = row_to_project(row)

    assert project["slug"] == "vinhomes-grand-park"
    assert project["total_units"] == 10000
    assert project["amenities"] == ["Hồ bơi", "Gym", "Công viên"]


def test_row_to_project_handles_missing_amenities_and_units():
    row = {"slug": "x", "name": "X", "url": "u"}

    project = row_to_project(row)

    assert project["total_units"] is None
    assert project["amenities"] == []
```

- [ ] **Step 4: Run tests and confirm failure**

```powershell
cd backend
python -m pytest tests/test_clean_project.py -q
```

Expected: fail because `row_to_project` does not exist.

- [ ] **Step 5: Add `row_to_project` to `data_pipeline/clean.py`**

```python
import json


def row_to_project(row: dict) -> dict:
    raw_amenities = row.get("amenities") or "[]"
    try:
        amenities = json.loads(raw_amenities) if isinstance(raw_amenities, str) else list(raw_amenities)
    except json.JSONDecodeError:
        amenities = []

    total_units_value = row.get("total_units")
    try:
        total_units = int(total_units_value) if total_units_value not in (None, "") else None
    except (TypeError, ValueError):
        total_units = None

    return {
        "slug": (row.get("slug") or "").strip(),
        "name": (row.get("name") or "").strip(),
        "developer": (row.get("developer") or "").strip() or None,
        "location": row.get("location") or None,
        "district": row.get("district") or None,
        "city": row.get("city") or None,
        "total_units": total_units,
        "price_range": row.get("price_range") or None,
        "area_range": row.get("area_range") or None,
        "status": row.get("status") or None,
        "project_type": row.get("project_type") or None,
        "description": row.get("description") or None,
        "amenities": [str(item).strip() for item in amenities if str(item).strip()],
        "url": row.get("url") or None,
    }
```

- [ ] **Step 6: Write failing ingestor row test**

Create `backend/tests/test_projects_ingestor.py`:

```python
from data_pipeline.ingestors.projects_ingestor import build_project_chunks


def test_build_project_chunks_creates_overview_and_amenities_chunks():
    project = {
        "slug": "vinhomes-grand-park",
        "name": "Vinhomes Grand Park",
        "developer": "Vinhomes",
        "district": "Quận 9",
        "city": "Hồ Chí Minh",
        "price_range": "2,5 - 4,8 tỷ",
        "area_range": "55 - 120 m²",
        "status": "selling",
        "description": "Khu đô thị tích hợp.",
        "amenities": ["Hồ bơi", "Công viên"],
    }

    chunks = build_project_chunks(project)
    chunk_types = [chunk["chunk_type"] for chunk in chunks]

    assert "overview" in chunk_types
    assert "description" in chunk_types
    assert "amenities" in chunk_types
```

- [ ] **Step 7: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_projects_ingestor.py -q
```

Expected: fail because `data_pipeline.ingestors.projects_ingestor` does not exist.

- [ ] **Step 8: Implement projects ingestor**

Create `data_pipeline/ingestors/projects_ingestor.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import Base, async_session, engine
from app.models import Chunk, Project
from data_pipeline.clean import row_to_project
from data_pipeline.embed import GeminiEmbedder


def build_project_chunks(project: dict) -> list[dict]:
    chunks: list[dict] = []
    overview_parts = [
        project.get("name"),
        f"Chủ đầu tư: {project.get('developer')}" if project.get("developer") else "",
        f"Khu vực: {project.get('district')}, {project.get('city')}".strip(", "),
        f"Trạng thái: {project.get('status')}" if project.get("status") else "",
        f"Giá: {project.get('price_range')}" if project.get("price_range") else "",
        f"Diện tích: {project.get('area_range')}" if project.get("area_range") else "",
    ]
    overview = ". ".join(part for part in overview_parts if part)
    if overview:
        chunks.append({"chunk_type": "overview", "text": overview})

    description = (project.get("description") or "").strip()
    if description:
        chunks.append({"chunk_type": "description", "text": description})

    amenities = project.get("amenities") or []
    if amenities:
        chunks.append({"chunk_type": "amenities", "text": "Tiện ích: " + ", ".join(amenities)})

    return chunks


async def upsert_project(session, project_data: dict) -> Project:
    slug = project_data["slug"]
    result = await session.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if project is None:
        project = Project(**project_data)
        session.add(project)
        await session.flush()
        return project
    for key, value in project_data.items():
        setattr(project, key, value)
    await session.flush()
    return project


async def ingest_project_rows(rows: list[dict], batch_size: int = 25) -> dict:
    settings = get_settings()
    embedder = GeminiEmbedder(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_EMBEDDING_MODEL)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    inserted = 0
    chunks_inserted = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        async with async_session() as session:
            for row in batch:
                project_data = row_to_project(row)
                if not project_data.get("slug"):
                    continue
                project = await upsert_project(session, project_data)

                chunks = build_project_chunks(project_data)
                vectors = await embedder.embed_texts([chunk["text"] for chunk in chunks])
                await session.execute(
                    delete(Chunk).where(Chunk.parent_type == "project", Chunk.parent_id == project.id)
                )
                session.add_all(
                    [
                        Chunk(
                            parent_type="project",
                            parent_id=project.id,
                            chunk_type=chunk["chunk_type"],
                            text=chunk["text"],
                            embedding=vector,
                        )
                        for chunk, vector in zip(chunks, vectors, strict=True)
                    ]
                )
                inserted += 1
                chunks_inserted += len(chunks)
            await session.commit()
    return {"projects": inserted, "chunks": chunks_inserted}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()
    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    print(await ingest_project_rows(rows, batch_size=args.batch_size))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 9: Run all project tests**

```powershell
cd backend
python -m pytest tests/test_clean_project.py tests/test_projects_ingestor.py -q
```

Expected: pass.

- [ ] **Step 10: Commit**

```powershell
git add crawler/projects data_pipeline/clean.py data_pipeline/ingestors/projects_ingestor.py backend/tests/test_clean_project.py backend/tests/test_projects_ingestor.py
git commit -m "add project crawler and ingestor"
```

---

### Task 8: News Crawler And Ingestor

**Files:**
- Create: `crawler/news/__init__.py`, `crawler/news/crawl_articles.py`
- Modify: `data_pipeline/clean.py`
- Create: `data_pipeline/ingestors/news_ingestor.py`
- Test: `backend/tests/test_clean_article.py`, `backend/tests/test_news_ingestor.py`

- [ ] **Step 1: Article URL+content crawler**

Create `crawler/news/crawl_articles.py` that lists `/tin-tuc` index pages and visits each article URL to extract `title`, `body`, `category`, `post_date`, `url`. Output columns: `title, body, category, post_date, url`. Reuse `crawler.core.csv_writer` and `crawler.core.parser.text_or_empty`.

- [ ] **Step 2: Write failing tests for `row_to_article`**

Create `backend/tests/test_clean_article.py`:

```python
from datetime import date

from data_pipeline.clean import row_to_article


def test_row_to_article_parses_iso_date():
    row = {
        "title": "Thị trường BĐS quý 1 2026",
        "body": "Báo cáo thị trường...",
        "category": "news",
        "post_date": "2026-04-15",
        "url": "https://batdongsan.com.vn/tin-tuc/q1-2026",
    }

    article = row_to_article(row)

    assert article["title"] == "Thị trường BĐS quý 1 2026"
    assert article["category"] == "news"
    assert article["post_date"] == date(2026, 4, 15)


def test_row_to_article_returns_none_post_date_for_invalid_input():
    article = row_to_article({"title": "T", "body": "B", "url": "u", "post_date": "không rõ"})
    assert article["post_date"] is None
```

- [ ] **Step 3: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_clean_article.py -q
```

Expected: fail because `row_to_article` does not exist.

- [ ] **Step 4: Add `row_to_article` to `data_pipeline/clean.py`**

```python
from datetime import date


def _parse_iso_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def row_to_article(row: dict) -> dict:
    return {
        "title": (row.get("title") or "").strip(),
        "body": (row.get("body") or "").strip(),
        "category": (row.get("category") or "news").strip() or "news",
        "source": "batdongsan.com",
        "post_date": _parse_iso_date(row.get("post_date") or ""),
        "url": row.get("url") or None,
    }
```

- [ ] **Step 5: Write failing news ingestor test**

Create `backend/tests/test_news_ingestor.py`:

```python
from data_pipeline.ingestors.news_ingestor import build_article_chunks


def test_build_article_chunks_splits_long_body_with_overlap():
    body = "Câu một. " * 200
    article = {"title": "Tiêu đề", "body": body, "category": "news"}

    chunks = build_article_chunks(article, chunk_size=120, overlap=20)

    assert len(chunks) > 1
    assert all(len(chunk["text"]) <= 200 for chunk in chunks)
    assert chunks[0]["chunk_type"] == "title"
    assert chunks[1]["chunk_type"] == "body"


def test_build_article_chunks_returns_only_title_when_body_empty():
    article = {"title": "Tiêu đề", "body": "", "category": "news"}

    chunks = build_article_chunks(article, chunk_size=120, overlap=20)

    assert [chunk["chunk_type"] for chunk in chunks] == ["title"]
```

- [ ] **Step 6: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_news_ingestor.py -q
```

Expected: fail because `data_pipeline.ingestors.news_ingestor` does not exist.

- [ ] **Step 7: Implement news ingestor**

Create `data_pipeline/ingestors/news_ingestor.py`:

```python
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import Base, async_session, engine
from app.models import Article, Chunk
from data_pipeline.clean import row_to_article
from data_pipeline.embed import GeminiEmbedder


def build_article_chunks(article: dict, *, chunk_size: int = 800, overlap: int = 120) -> list[dict]:
    chunks: list[dict] = []
    title = (article.get("title") or "").strip()
    body = (article.get("body") or "").strip()

    if title:
        chunks.append({"chunk_type": "title", "text": title})

    if not body:
        return chunks

    step = max(chunk_size - overlap, 1)
    for start in range(0, len(body), step):
        piece = body[start : start + chunk_size]
        if piece.strip():
            chunks.append({"chunk_type": "body", "text": piece})
        if start + chunk_size >= len(body):
            break
    return chunks


async def upsert_article(session, article_data: dict) -> Article:
    url = article_data["url"]
    result = await session.execute(select(Article).where(Article.url == url))
    article = result.scalar_one_or_none()
    if article is None:
        article = Article(**article_data)
        session.add(article)
        await session.flush()
        return article
    for key, value in article_data.items():
        setattr(article, key, value)
    await session.flush()
    return article


async def ingest_article_rows(rows: list[dict]) -> dict:
    settings = get_settings()
    embedder = GeminiEmbedder(api_key=settings.GEMINI_API_KEY, model=settings.GEMINI_EMBEDDING_MODEL)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    inserted = 0
    chunks_total = 0
    async with async_session() as session:
        for row in rows:
            article_data = row_to_article(row)
            if not article_data.get("url"):
                continue
            article = await upsert_article(session, article_data)
            chunks = build_article_chunks(article_data)
            vectors = await embedder.embed_texts([chunk["text"] for chunk in chunks])
            await session.execute(
                delete(Chunk).where(Chunk.parent_type == "article", Chunk.parent_id == article.id)
            )
            session.add_all(
                [
                    Chunk(
                        parent_type="article",
                        parent_id=article.id,
                        chunk_type=chunk["chunk_type"],
                        text=chunk["text"],
                        embedding=vector,
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ]
            )
            inserted += 1
            chunks_total += len(chunks)
        await session.commit()
    return {"articles": inserted, "chunks": chunks_total}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    args = parser.parse_args()
    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    print(await ingest_article_rows(rows))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 8: Run news tests**

```powershell
cd backend
python -m pytest tests/test_clean_article.py tests/test_news_ingestor.py -q
```

Expected: pass.

- [ ] **Step 9: Commit**

```powershell
git add crawler/news data_pipeline/clean.py data_pipeline/ingestors/news_ingestor.py backend/tests/test_clean_article.py backend/tests/test_news_ingestor.py
git commit -m "add news crawler and ingestor"
```

---

### Task 9: Hybrid Search For Projects And Articles

**Files:**
- Modify: `chatbot/tools/hybrid_search.py`
- Test: `backend/tests/test_hybrid_search_multi_parent.py`

- [ ] **Step 1: Write failing test for parent-type dispatch**

Create `backend/tests/test_hybrid_search_multi_parent.py`:

```python
import pytest

from chatbot.tools.hybrid_search import build_project_filter_clauses, build_article_filter_clauses


def test_build_project_filter_clauses_supports_status_and_city():
    clauses, params = build_project_filter_clauses({"status": "selling", "city": "Hồ Chí Minh"})

    sql = " ".join(clauses)
    assert "status = :status" in sql
    assert "city ILIKE :city" in sql
    assert params["city"] == "%Hồ Chí Minh%"


def test_build_article_filter_clauses_supports_category():
    clauses, params = build_article_filter_clauses({"category": "news"})

    assert "category = :category" in " ".join(clauses)
    assert params["category"] == "news"
```

- [] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_hybrid_search_multi_parent.py -q
```

Expected: fail because the new builder helpers do not exist.

- [ ] **Step 3: Add helpers and dispatch in `chatbot/tools/hybrid_search.py`**

```python
def build_project_filter_clauses(filters: dict) -> tuple[list[str], dict]:
    clauses: list[str] = []
    params: dict = {}
    if filters.get("status"):
        clauses.append("status = :status")
        params["status"] = filters["status"]
    if filters.get("city"):
        clauses.append("city ILIKE :city")
        params["city"] = f"%{filters['city']}%"
    if filters.get("district"):
        clauses.append("district ILIKE :district")
        params["district"] = f"%{filters['district']}%"
    if filters.get("project_type"):
        clauses.append("project_type ILIKE :project_type")
        params["project_type"] = f"%{filters['project_type']}%"
    return clauses or ["1=1"], params


def build_article_filter_clauses(filters: dict) -> tuple[list[str], dict]:
    clauses: list[str] = []
    params: dict = {}
    if filters.get("category"):
        clauses.append("category = :category")
        params["category"] = filters["category"]
    return clauses or ["1=1"], params
```

Update `sql_filter` to dispatch by `parent_type`:

```python
async def sql_filter(parent_type: str, filters: dict, limit: int = 500) -> list[int]:
    if parent_type == "listing":
        clauses, params = build_listing_filter_clauses(filters)
        table = "listings"
        order_by = "ORDER BY updated_at DESC NULLS LAST, id DESC"
    elif parent_type == "project":
        clauses, params = build_project_filter_clauses(filters)
        table = "projects"
        order_by = "ORDER BY updated_at DESC NULLS LAST, id DESC"
    elif parent_type == "article":
        clauses, params = build_article_filter_clauses(filters)
        table = "articles"
        order_by = "ORDER BY post_date DESC NULLS LAST, id DESC"
    else:
        return []

    params["limit"] = limit
    query = text(
        f"SELECT id FROM {table} WHERE {' AND '.join(clauses)} {order_by} LIMIT :limit"
    )
    async with async_session() as session:
        result = await session.execute(query, params)
        return [row[0] for row in result.all()]
```

Add `resolve_to_project_records` and `resolve_to_article_records` mirroring `resolve_to_listing_records` but selecting from `projects` and `articles` respectively. Update the bottom of `hybrid_search` to dispatch:

```python
    if parent_type == "listing":
        return await resolve_to_listing_records(reranked)
    if parent_type == "project":
        return await resolve_to_project_records(reranked)
    if parent_type == "article":
        return await resolve_to_article_records(reranked)
    return []
```

- [ ] **Step 4: Run filter tests**

```powershell
cd backend
python -m pytest tests/test_hybrid_search.py tests/test_hybrid_search_multi_parent.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add chatbot/tools/hybrid_search.py backend/tests/test_hybrid_search_multi_parent.py
git commit -m "support project and article parent types in hybrid search"
```

---

### Task 10: Market Stats Tool And Market Analysis Agent

**Files:**
- Create: `chatbot/tools/market_stats.py`
- Modify: `chatbot/agents/market_analysis.py`
- Test: `backend/tests/test_market_stats.py`

- []**Step 1: Write failing test for SQL builder**

Create `backend/tests/test_market_stats.py`:

```python
from chatbot.tools.market_stats import build_district_price_query


def test_build_district_price_query_includes_filters():
    sql, params = build_district_price_query(city="Hồ Chí Minh", listing_type="sale", property_type="apartment")

    assert "AVG(price)" in sql
    assert "AVG(price_per_m2)" in sql
    assert "city = :city" in sql
    assert params == {"city": "Hồ Chí Minh", "listing_type": "sale", "property_type": "%apartment%"}
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_market_stats.py -q
```

Expected: fail because `chatbot.tools.market_stats` does not exist.

- [ ] **Step 3: Implement `market_stats.py`**

```python
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import async_session


def build_district_price_query(*, city: str, listing_type: str, property_type: str | None = None) -> tuple[str, dict]:
    clauses = [
        "is_active = true",
        "city = :city",
        "listing_type = :listing_type",
        "price IS NOT NULL",
    ]
    params: dict = {"city": city, "listing_type": listing_type}
    if property_type:
        clauses.append("property_type ILIKE :property_type")
        params["property_type"] = f"%{property_type}%"

    sql = (
        "SELECT district, COUNT(*) AS listings, "
        "AVG(price) AS avg_price, AVG(price_per_m2) AS avg_price_per_m2 "
        "FROM listings "
        f"WHERE {' AND '.join(clauses)} "
        "GROUP BY district "
        "ORDER BY avg_price_per_m2 DESC NULLS LAST"
    )
    return sql, params


async def district_price_overview(city: str, listing_type: str, property_type: str | None = None) -> list[dict]:
    sql, params = build_district_price_query(city=city, listing_type=listing_type, property_type=property_type)
    async with async_session() as session:
        result = await session.execute(text(sql), params)
        return [dict(row._mapping) for row in result.all()]
```

- [ ] **Step 4: Wire Market Analysis Agent**

Replace `market_analysis_node` in `chatbot/agents/market_analysis.py`:

```python
from chatbot.state import ChatState
from chatbot.tools.market_stats import district_price_overview


async def market_analysis_node(state: ChatState) -> dict:
    filters = state.get("search_filters", {})
    city = filters.get("city") or "Hồ Chí Minh"
    listing_type = filters.get("listing_type") or "sale"
    property_type = filters.get("property_type")

    rows = await district_price_overview(city=city, listing_type=listing_type, property_type=property_type)
    if not rows:
        content = f"Chưa đủ dữ liệu để phân tích {city} ({listing_type})."
    else:
        lines = [f"Phân tích giá theo quận tại {city} ({listing_type}):"]
        for row in rows[:10]:
            lines.append(
                f"- {row['district']}: {row['listings']} tin, "
                f"giá TB {row['avg_price']:.2f} tỷ, giá/m² TB {row['avg_price_per_m2']:.2f} triệu"
            )
        content = "\n".join(lines)

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "market_analysis": {
                "agent_name": "market_analysis",
                "content": content,
                "sources": [],
                "confidence": 0.7 if rows else 0.3,
            },
        },
    }
```

- [ ] **Step 5: Run market stats tests**

```powershell
cd backend
python -m pytest tests/test_market_stats.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add chatbot/tools/market_stats.py chatbot/agents/market_analysis.py backend/tests/test_market_stats.py
git commit -m "wire market analysis agent to listings aggregates"
```

---

### Task 11: Property Search Forwards listing_type

**Files:**
- Modify: `chatbot/agents/property_search.py`
- Test: `backend/tests/test_property_search_listing_type.py`

-[]**Step 1: Write failing test ensuring rent filter is forwarded**

Create `backend/tests/test_property_search_listing_type.py`:

```python
import pytest

from chatbot.agents import property_search


@pytest.mark.asyncio
async def test_property_search_forwards_listing_type(monkeypatch):
    captured = {}

    async def fake_hybrid(query, filters, parent_type):
        captured.update({"query": query, "filters": filters, "parent_type": parent_type})
        return []

    monkeypatch.setattr(property_search, "hybrid_search", fake_hybrid)

    state = {
        "user_query": "Cho thuê căn hộ Quận 7",
        "search_filters": {"listing_type": "rent", "district": "Quận 7"},
        "agent_results": {},
    }

    await property_search.property_search_node(state)

    assert captured["filters"]["listing_type"] == "rent"
    assert captured["filters"]["district"] == "Quận 7"
    assert captured["parent_type"] == "listing"
```

- [ ] **Step 2: Run the test and confirm failure**

```powershell
cd backend
python -m pytest tests/test_property_search_listing_type.py -q
```

Expected: pass already if M1 forwards the entire `filters` dict; otherwise fail and adjust the agent to call `hybrid_search(query=query, filters=filters, parent_type="listing")` exactly. If the test passes, leave the agent unchanged and skip Step 3.

- [ ] **Step 3: Adjust agent if necessary**

Confirm the call inside `property_search_node` is:

```python
listings = await hybrid_search(query=query, filters=filters, parent_type="listing")
```

- [ ] **Step 4: Commit**

```powershell
git add chatbot/agents/property_search.py backend/tests/test_property_search_listing_type.py
git commit -m "verify property search forwards listing type"
```

---

### Task 12: Geocode Index Migration

**Files:**
- Create: `backend/alembic/versions/20260601_0002_m2_geocode_indexes.py`

- [ ] **Step 1: Add migration**

Create the file with:

```python
"""m2 geocode and project indexes

Revision ID: 20260601_0002
Revises: 20260525_0001
Create Date: 2026-06-01 00:00:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260601_0002"
down_revision: Union[str, None] = "20260525_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_listings_city_district", "listings", ["city", "district"], unique=False)
    op.create_index("ix_listings_lat_lon", "listings", ["latitude", "longitude"], unique=False)
    op.create_index("ix_projects_city_district", "projects", ["city", "district"], unique=False)
    op.create_index("ix_articles_post_date", "articles", ["post_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_articles_post_date", table_name="articles")
    op.drop_index("ix_projects_city_district", table_name="projects")
    op.drop_index("ix_listings_lat_lon", table_name="listings")
    op.drop_index("ix_listings_city_district", table_name="listings")
```

- [ ] **Step 2: Apply migration locally**

```powershell
cd backend
alembic upgrade head
```

Expected: revision `20260601_0002` applied without errors.

- [ ] **Step 3: Commit**

```powershell
git add backend/alembic/versions/20260601_0002_m2_geocode_indexes.py
git commit -m "add m2 geocode and project indexes"
```

---

### Task 13: M2 End-To-End Verification

**Files:**
- No required code changes unless a previous task failed verification.

- [ ] **Step 1: Run all M1 + M2 tests**

```powershell
cd backend
python -m pytest tests -q
```

Expected: all pass.

- [ ] **Step 2: Apply migrations**

```powershell
cd backend
alembic upgrade head
```

Expected: revisions up to `20260601_0002` applied.

- [ ] **Step 3: Ingest sale + rent + projects + news samples**

After setting `GEMINI_API_KEY`:

```powershell
python -m data_pipeline.ingestors.listings_ingestor --csv data\listing_details.csv --batch-size 5
python -m data_pipeline.ingestors.listings_ingestor --csv data\rent_details.csv --batch-size 5
python -m data_pipeline.ingestors.projects_ingestor --csv data\projects.csv --batch-size 5
python -m data_pipeline.ingestors.news_ingestor --csv data\news.csv
```

Expected: each command prints nonzero counts and exits cleanly. Use any small CSV samples that exist locally; if a CSV is missing, capture a 1-page sample with the matching M2 crawler first.

- [ ] **Step 4: Confirm geocoded coordinates**

Run:

```powershell
docker exec -it realestate_postgres psql -U admin -d realestate -c "SELECT count(*) FILTER (WHERE latitude IS NOT NULL) AS geocoded, count(*) FROM listings;"
```

Expected: `geocoded` is greater than zero. If zero, check Nominatim rate limits and `GEOCODER_USER_AGENT`.

- [ ] **Step 5: Hybrid search across parent types**

```powershell
python -m chatbot.tools.hybrid_search --query "căn hộ cho thuê Quận 7"
```

Manually invoke the project and article paths from a Python REPL:

```powershell
python -c "import asyncio; from chatbot.tools.hybrid_search import hybrid_search; print(asyncio.run(hybrid_search('Vinhomes Grand Park', filters={'status':'selling'}, parent_type='project')))"
python -c "import asyncio; from chatbot.tools.hybrid_search import hybrid_search; print(asyncio.run(hybrid_search('thị trường BĐS quý 1', filters={'category':'news'}, parent_type='article')))"
```

Expected: each call returns a non-empty list when matching data exists.

- [ ] **Step 6: Market analysis smoke test**

```powershell
python -c "import asyncio; from chatbot.tools.market_stats import district_price_overview; print(asyncio.run(district_price_overview(city='Hồ Chí Minh', listing_type='sale')))"
```

Expected: list of districts with averaged price metrics.

- [ ] **Step 7: Commit verification fixes**

If any verification step required code changes:

```powershell
git add <changed-files>
git commit -m "fix m2 verification issues"
```

---

## Self-Review

- Spec coverage: M2 ships rent crawler (Task 3), shared listing detail parser (Task 2), geocoding + intent extraction (Tasks 4–6), project crawler/ingestor (Task 7), news crawler/ingestor (Task 8), hybrid search across parent types (Task 9), market analysis SQL aggregates (Task 10), rent forwarding through Property Search Agent (Task 11), the index migration (Task 12), and end-to-end verification (Task 13). Legal PDFs and Airflow remain in M3/M4.
- Placeholder scan: every step lists concrete files, runnable commands, and code blocks. The Nominatim user-agent string is a deployment placeholder that the user should replace with a real contact email before going live; this is called out in scope notes, not buried in code.
- Type consistency: chunks across listings/projects/articles share the `parent_type`, `parent_id`, `chunk_type`, `text`, `embedding` shape; `row_to_listing`, `row_to_project`, `row_to_article` all return plain `dict`s consumed by the matching `*_ingestor.py`.
- Known limits accepted in M2: Nominatim is rate-limited to 1 req/s and may miss obscure addresses; Gemini-based intent extraction is opt-in via `INTENT_EXTRACTOR=gemini`; news ingestion does not deduplicate near-duplicate articles beyond `(url)`; rerank still depends on Cohere being configured.
