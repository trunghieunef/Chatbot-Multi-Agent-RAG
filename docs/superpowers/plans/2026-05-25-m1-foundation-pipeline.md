# M1 Foundation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the M1 sale-only foundation pipeline so existing sale crawler CSV data can be cleaned, chunked, embedded into PostgreSQL/pgvector, and queried by the chatbot through a hybrid SQL + vector retriever.

**Architecture:** Keep PostgreSQL 16 + pgvector as the source of truth. Refactor reusable cleaning/chunk/embed logic into `data_pipeline/`, add `articles` and `chunks` ORM models plus Alembic, then expose `chatbot/tools/hybrid_search.py` for agents. M1 intentionally keeps crawling sale-only and manual CLI execution; rent, projects/news crawlers, Airflow, and legal PDF ingestion are separate milestones.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, Alembic, pgvector, Google Gemini `text-embedding-004`, optional Cohere rerank, Playwright crawler code already in `Crawl/`.

---

## Scope And Existing Repo Notes

- Existing `backend/app/models/project.py` already defines `Project`; do not create a duplicate. M1 only adds `Article` and `Chunk`, and keeps `Project.embedding` unchanged for now.
- Existing `backend/app/models/listing.py` already has `embedding = Vector(768)`. M1 stores retrieval embeddings in `chunks.embedding`; do not rely on `listings.embedding` for chatbot retrieval.
- Existing `docker-compose.yml` already uses `pgvector/pgvector:pg16`; no M1 compose image change is required.
- Existing `data_pipeline/load_db.py` contains parser functions that must move to `data_pipeline/clean.py`.
- Existing `chatbot/agents/property_search.py`, `market_analysis.py`, and `legal_advisor.py` are placeholders. M1 wires only `property_search` to real listing search after `hybrid_search.py` exists.
- Existing `chatbot/config.py` uses `models/text-embedding-004`, while `backend/app/config.py` defaults to `gemini-embedding-2`. M1 must normalize both to `models/text-embedding-004`.
- Use `PYTHONPATH=backend` or run from `backend/` when importing `app.*`. Pipeline modules should add `backend/` to `sys.path` in CLI entrypoints so `python -m data_pipeline...` works from repo root.
- Tests under `backend/tests/` import from `data_pipeline`, `chatbot`, and `crawler`, which live at the repo root. The current `backend/tests/conftest.py` only adds `backend/` to `sys.path`, so those imports fail. Task 0 below fixes conftest before any other test task runs.
- M1 defers `data_pipeline/enrich.py` (geocoding via Nominatim/Goong, LLM-based intent extraction) to M2. Listings ingested in M1 leave `latitude` and `longitude` NULL. The rule-based `extract_intent_tags` inside `data_pipeline/chunk.py` is a deliberate stand-in.
- The legacy `Listing.embedding` column at `backend/app/models/listing.py:76` is intentionally left in place and unused. Hybrid retrieval reads only `chunks.embedding`. Dropping the column is scheduled for a later milestone migration, not M1.
- The Cohere call inside `cohere_rerank` is gated on `COHERE_API_KEY` being set. When unset, `hybrid_search` falls back to vector-distance ordering. Verify the v2 payload schema (`https://api.cohere.com/v2/rerank`) against current Cohere docs before turning the key on; if the schema changed, only the rerank stage is affected and the rest of M1 still works.

## File Structure

- Create: `data_pipeline/clean.py`  
  Owns CSV field parsing and row normalization for listings.
- Create: `data_pipeline/chunk.py`  
  Builds deterministic semantic chunks for listings.
- Create: `data_pipeline/embed.py`  
  Wraps Gemini embedding calls with batching, retry, and testable client injection.
- Create: `data_pipeline/ingestors/__init__.py`  
  Marks ingestors as a package.
- Create: `data_pipeline/ingestors/listings_ingestor.py`  
  CLI orchestration for clean -> upsert listing -> delete old chunks -> embed chunks -> insert chunks.
- Modify: `data_pipeline/load_db.py`  
  Keep backward-compatible CLI by delegating to `listings_ingestor.py`.
- Create: `backend/app/models/article.py`  
  ORM model for future news/legal parent records.
- Create: `backend/app/models/chunk.py`  
  ORM model for chunked vector retrieval.
- Modify: `backend/app/models/__init__.py`  
  Export `Article` and `Chunk`.
- Modify: `backend/app/config.py`  
  Add embedding/rerank settings.
- Modify: `chatbot/config.py`  
  Mirror embedding/rerank constants used by chatbot tools.
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, `backend/alembic/versions/20260525_0001_m1_foundation.py`  
  Alembic setup and first migration for `articles`, `chunks`, and pgvector extension.
- Create: `chatbot/tools/__init__.py`
- Create: `chatbot/tools/hybrid_search.py`  
  SQL filter -> pgvector kNN -> rerank -> resolve parent records.
- Modify: `chatbot/agents/property_search.py`  
  Call `hybrid_search(parent_type="listing")` and format top results.
- Modify: `backend/requirements.txt`  
  Add `alembic` and rerank HTTP dependency if missing.
- Create tests under `backend/tests/` for clean/chunk/embed/hybrid SQL filter.
- Modify: `backend/tests/conftest.py`
  Add the repo root to `sys.path` so tests can import `data_pipeline`, `chatbot`, and `crawler`.

---

### Task 0: Fix Test Import Paths

**Files:**
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_conftest_paths.py`

The current `backend/tests/conftest.py` only adds `backend/` to `sys.path`. M1 tests import from repo-root packages (`data_pipeline`, `chatbot`, `crawler`), so they fail with `ModuleNotFoundError`. Fix this first so every later TDD task can actually run.

- [ ] **Step 1: Write a failing path test**

Create `backend/tests/test_conftest_paths.py`:

```python
import importlib


def test_repo_root_packages_are_importable():
    importlib.import_module("data_pipeline")
    importlib.import_module("chatbot")
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```powershell
cd backend
python -m pytest tests/test_conftest_paths.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'data_pipeline'`.

- [ ] **Step 3: Update conftest to add repo root**

Replace `backend/tests/conftest.py` with:

```python
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

for path in (REPO_ROOT, BACKEND_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
```

- [ ] **Step 4: Add `__init__.py` files to repo-root packages if missing**

Run:

```powershell
python -c "import data_pipeline, chatbot; print('ok')"
```

If either import fails because `__init__.py` is missing, create empty `data_pipeline/__init__.py` or `chatbot/__init__.py`. The repo already ships these, so this is a defensive check.

- [ ] **Step 5: Run the path test**

Run:

```powershell
cd backend
python -m pytest tests/test_conftest_paths.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add backend/tests/conftest.py backend/tests/test_conftest_paths.py
git commit -m "fix test import paths for repo-root packages"
```

---

### Task 1: Configuration And Dependencies

**Files:**
- Modify: `backend/app/config.py`
- Modify: `chatbot/config.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_pipeline_config.py`

- [ ] **Step 1: Write the failing config test**

Create `backend/tests/test_pipeline_config.py`:

```python
from app.config import Settings


def test_pipeline_defaults_use_m1_embedding_model():
    settings = Settings()

    assert settings.GEMINI_EMBEDDING_MODEL == "models/text-embedding-004"
    assert settings.EMBEDDING_DIM == 768
    assert settings.CHUNK_SIZE_TOKENS == 400
    assert settings.RERANK_PROVIDER == "cohere"
    assert settings.RERANK_TOP_N == 5
```

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```powershell
cd backend
python -m pytest tests/test_pipeline_config.py -q
```

Expected: fail because `Settings` does not define `EMBEDDING_DIM`, `CHUNK_SIZE_TOKENS`, `RERANK_PROVIDER`, or `RERANK_TOP_N`, and the embedding model default is different.

- [ ] **Step 3: Add config fields**

Modify `backend/app/config.py` inside `Settings`:

```python
    # Google Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    GEMINI_EMBEDDING_MODEL: str = "models/text-embedding-004"
    EMBEDDING_DIM: int = 768
    CHUNK_SIZE_TOKENS: int = 400
    CHUNK_OVERLAP_TOKENS: int = 80

    # Reranking
    COHERE_API_KEY: str = ""
    RERANK_PROVIDER: str = "cohere"
    RERANK_MODEL: str = "rerank-multilingual-v3.0"
    RERANK_TOP_N: int = 5
```

Modify `chatbot/config.py` so chatbot tools have matching constants:

```python
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "400"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "80"))

COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
RERANK_PROVIDER = os.getenv("RERANK_PROVIDER", "cohere")
RERANK_MODEL = os.getenv("RERANK_MODEL", "rerank-multilingual-v3.0")
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", "5"))
```

Modify `backend/requirements.txt` by adding:

```text
alembic>=1.14.0
httpx>=0.28.0
```

- [ ] **Step 4: Run the config test**

Run:

```powershell
cd backend
python -m pytest tests/test_pipeline_config.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/config.py chatbot/config.py backend/requirements.txt backend/tests/test_pipeline_config.py
git commit -m "configure m1 pipeline settings"
```

---

### Task 2: Extract Listing Cleaning Logic

**Files:**
- Create: `data_pipeline/clean.py`
- Modify: `data_pipeline/load_db.py`
- Test: `backend/tests/test_clean.py`

- [ ] **Step 1: Write parser and normalization tests**

Create `backend/tests/test_clean.py`:

```python
from data_pipeline.clean import (
    determine_listing_type,
    determine_property_type,
    extract_location,
    parse_area,
    parse_int_safe,
    parse_price_billion,
    parse_price_per_m2,
    row_to_listing,
)


def test_parse_vietnamese_price_units_to_billions():
    assert parse_price_billion("4,68 tỷ") == 4.68
    assert parse_price_billion("850 triệu") == 0.85
    assert parse_price_billion("120 nghìn") == 0.00012
    assert parse_price_billion("") is None


def test_parse_area_and_int_fields():
    assert parse_area("72,5 m²") == 72.5
    assert parse_area("không rõ") is None
    assert parse_int_safe("3 phòng ngủ") == 3
    assert parse_int_safe("") is None


def test_listing_type_and_property_type_rules():
    assert determine_listing_type({"title": "Cho thuê căn hộ", "url": "", "price_text": "15 triệu/tháng"}) == "rent"
    assert determine_listing_type({"title": "Bán nhà Quận 7", "url": "/nha-dat-ban", "price_text": "6 tỷ"}) == "sale"
    assert determine_property_type({"title": "Căn hộ chung cư 2PN", "property_type": ""}) == "Căn hộ chung cư"
    assert determine_property_type({"title": "Bán đất nền", "property_type": ""}) == "Đất nền"


def test_extract_location_from_address_tail():
    row = {"address": "Đường Nguyễn Văn Linh, Phường Tân Phong, Quận 7, Hồ Chí Minh"}
    assert extract_location(row) == ("Phường Tân Phong", "Quận 7", "Hồ Chí Minh")


def test_row_to_listing_maps_csv_fields():
    row = {
        "product_id": "123",
        "title": "Bán căn hộ 2PN Quận 7",
        "description": "Gần trường học, pháp lý rõ ràng",
        "price_text": "4,5 tỷ",
        "price_per_m2_text": "60 triệu/m²",
        "area_text": "75 m²",
        "bedrooms": "2 PN",
        "bathrooms": "2 WC",
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "url": "https://batdongsan.com.vn/listing-123",
    }

    listing = row_to_listing(row)

    assert listing["product_id"] == "123"
    assert listing["listing_type"] == "sale"
    assert listing["property_type"] == "Căn hộ chung cư"
    assert listing["price"] == 4.5
    assert listing["area"] == 75
    assert listing["bedrooms"] == 2
    assert listing["district"] == "Quận 7"
```

- [ ] **Step 2: Run the tests and confirm import failure**

Run:

```powershell
cd backend
python -m pytest tests/test_clean.py -q
```

Expected: fail because `data_pipeline.clean` does not exist.

- [ ] **Step 3: Create `data_pipeline/clean.py`**

Move the current parser functions from `data_pipeline/load_db.py` into `data_pipeline/clean.py` with these public functions:

```python
PRICE_RE = re.compile(r"([\d.,]+)", re.IGNORECASE)

def parse_price_billion(text: str) -> float | None: ...
def parse_area(text: str) -> float | None: ...
def parse_int_safe(text: str) -> int | None: ...
def parse_price_per_m2(text: str) -> float | None: ...
def determine_listing_type(row: dict) -> str: ...
def determine_property_type(row: dict) -> str: ...
def extract_location(row: dict) -> tuple[str, str, str]: ...
def row_to_listing(row: dict) -> dict: ...
```

Keep behavior identical to the existing `load_db.py` functions, except return `"million/month"` as `price_unit` when `determine_listing_type(row) == "rent"` and the raw price contains `"/tháng"` or `"tháng"`.

- [ ] **Step 4: Modify `data_pipeline/load_db.py` imports**

Replace local parser definitions with:

```python
from data_pipeline.clean import row_to_listing
```

Remove duplicated parser functions from `load_db.py`. Leave `load_csv_to_db()` and `main()` in place until Task 6 replaces the implementation with a delegating wrapper.

- [ ] **Step 5: Run clean tests**

Run:

```powershell
cd backend
python -m pytest tests/test_clean.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add data_pipeline/clean.py data_pipeline/load_db.py backend/tests/test_clean.py
git commit -m "extract listing cleaning utilities"
```

---

### Task 3: Add Semantic Listing Chunk Builder

**Files:**
- Create: `data_pipeline/chunk.py`
- Test: `backend/tests/test_chunk.py`

- [ ] **Step 1: Write chunk tests**

Create `backend/tests/test_chunk.py`:

```python
from data_pipeline.chunk import build_listing_chunks


def test_build_listing_chunks_creates_expected_chunk_types():
    listing = {
        "title": "Bán căn hộ 2PN Quận 7",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4,5 tỷ",
        "area_text": "75 m²",
        "bedrooms": 2,
        "bathrooms": 2,
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "description": "Căn hộ gần trường học, gần siêu thị, an ninh tốt.",
        "legal_status": "Sổ hồng",
        "furniture": "Đầy đủ",
    }

    chunks = build_listing_chunks(listing)
    by_type = {chunk["chunk_type"]: chunk for chunk in chunks}

    assert set(by_type) == {"overview", "description", "location", "intent_tags"}
    assert "Bán căn hộ 2PN Quận 7" in by_type["overview"]["text"]
    assert "Quận 7" in by_type["location"]["text"]
    assert "gần trường" in by_type["intent_tags"]["text"]


def test_build_listing_chunks_skips_empty_description_chunk():
    listing = {
        "title": "Bán đất nền",
        "property_type": "Đất nền",
        "listing_type": "sale",
        "price_text": "",
        "area_text": "",
        "district": "",
        "city": "",
        "address": "",
        "description": "",
    }

    chunks = build_listing_chunks(listing)

    assert [chunk["chunk_type"] for chunk in chunks] == ["overview"]
```

- [ ] **Step 2: Run the tests and confirm import failure**

Run:

```powershell
cd backend
python -m pytest tests/test_chunk.py -q
```

Expected: fail because `data_pipeline.chunk` does not exist.

- [ ] **Step 3: Create `data_pipeline/chunk.py`**

Implement these functions:

```python
from __future__ import annotations

import re
from typing import Any


INTENT_RULES: dict[str, tuple[str, ...]] = {
    "gần trường": ("gần trường", "trường học", "đại học", "mầm non"),
    "gần chợ": ("gần chợ", "chợ", "siêu thị", "trung tâm thương mại"),
    "gần bệnh viện": ("bệnh viện", "phòng khám"),
    "an ninh": ("an ninh", "bảo vệ", "camera"),
    "view đẹp": ("view", "ban công", "sông", "công viên"),
    "pháp lý rõ": ("sổ hồng", "sổ đỏ", "pháp lý"),
}


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_intent_tags(text: str) -> list[str]:
    lowered = text.lower()
    tags: list[str] = []
    for tag, needles in INTENT_RULES.items():
        if any(needle in lowered for needle in needles):
            tags.append(tag)
    return tags


def build_listing_chunks(listing: dict[str, Any]) -> list[dict[str, str]]:
    title = compact_text(listing.get("title"))
    property_type = compact_text(listing.get("property_type"))
    listing_type = compact_text(listing.get("listing_type"))
    price_text = compact_text(listing.get("price_text"))
    area_text = compact_text(listing.get("area_text"))
    district = compact_text(listing.get("district"))
    city = compact_text(listing.get("city"))
    address = compact_text(listing.get("address"))
    description = compact_text(listing.get("description"))
    legal_status = compact_text(listing.get("legal_status"))
    furniture = compact_text(listing.get("furniture"))
    bedrooms = compact_text(listing.get("bedrooms"))
    bathrooms = compact_text(listing.get("bathrooms"))

    chunks: list[dict[str, str]] = []

    overview_parts = [
        title,
        f"Loại giao dịch: {listing_type}" if listing_type else "",
        f"Loại bất động sản: {property_type}" if property_type else "",
        f"Giá: {price_text}" if price_text else "",
        f"Diện tích: {area_text}" if area_text else "",
        f"Phòng ngủ: {bedrooms}" if bedrooms else "",
        f"Phòng tắm: {bathrooms}" if bathrooms else "",
        f"Khu vực: {district}, {city}".strip(", ") if district or city else "",
        f"Pháp lý: {legal_status}" if legal_status else "",
        f"Nội thất: {furniture}" if furniture else "",
    ]
    overview = ". ".join(part for part in overview_parts if part)
    if overview:
        chunks.append({"chunk_type": "overview", "text": overview})

    if description:
        chunks.append({"chunk_type": "description", "text": description})

    location_parts = [
        f"Địa chỉ: {address}" if address else "",
        f"Quận/Huyện: {district}" if district else "",
        f"Tỉnh/Thành phố: {city}" if city else "",
    ]
    location = ". ".join(part for part in location_parts if part)
    if location:
        chunks.append({"chunk_type": "location", "text": location})

    tags = extract_intent_tags(" ".join([title, description, address, legal_status, furniture]))
    if tags:
        chunks.append({"chunk_type": "intent_tags", "text": "Nhu cầu phù hợp: " + ", ".join(tags)})

    return chunks
```

- [ ] **Step 4: Run chunk tests**

Run:

```powershell
cd backend
python -m pytest tests/test_chunk.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/chunk.py backend/tests/test_chunk.py
git commit -m "add listing semantic chunk builder"
```

---

### Task 4: Add Testable Gemini Embedder

**Files:**
- Create: `data_pipeline/embed.py`
- Test: `backend/tests/test_embed.py`

- [ ] **Step 1: Write embedder tests using a fake client**

Create `backend/tests/test_embed.py`:

```python
import pytest

from data_pipeline.embed import GeminiEmbedder


class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeResult:
    def __init__(self, values):
        self.embeddings = [FakeEmbedding(row) for row in values]


class FakeModels:
    def __init__(self):
        self.calls = []

    def embed_content(self, model, contents):
        self.calls.append((model, contents))
        return FakeResult([[float(i)] * 768 for i, _ in enumerate(contents, start=1)])


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


@pytest.mark.asyncio
async def test_embed_texts_batches_and_returns_vectors():
    client = FakeClient()
    embedder = GeminiEmbedder(api_key="test", client=client, batch_size=2)

    vectors = await embedder.embed_texts(["a", "b", "c"])

    assert len(vectors) == 3
    assert len(vectors[0]) == 768
    assert client.models.calls == [
        ("models/text-embedding-004", ["a", "b"]),
        ("models/text-embedding-004", ["c"]),
    ]


@pytest.mark.asyncio
async def test_embed_texts_returns_empty_for_empty_input():
    embedder = GeminiEmbedder(api_key="test", client=FakeClient())

    assert await embedder.embed_texts([]) == []
```

- [ ] **Step 2: Run the tests and confirm import failure**

Run:

```powershell
cd backend
python -m pytest tests/test_embed.py -q
```

Expected: fail because `data_pipeline.embed` does not exist.

- [ ] **Step 3: Create `data_pipeline/embed.py`**

Implement an async wrapper with client injection:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Sequence

from google import genai


@dataclass
class GeminiEmbedder:
    api_key: str
    model: str = "models/text-embedding-004"
    batch_size: int = 100
    retries: int = 3
    retry_delay_seconds: float = 1.0
    client: object | None = None

    def __post_init__(self) -> None:
        if self.client is None:
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is required for embeddings")
            self.client = genai.Client(api_key=self.api_key)

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        clean_texts = [text for text in texts if text and text.strip()]
        if not clean_texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(clean_texts), self.batch_size):
            batch = clean_texts[start : start + self.batch_size]
            vectors.extend(await self._embed_batch_with_retry(batch))
        return vectors

    async def _embed_batch_with_retry(self, batch: Sequence[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                return await asyncio.to_thread(self._embed_batch_sync, batch)
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(self.retry_delay_seconds * (2**attempt))
        raise RuntimeError(f"Embedding failed after {self.retries} attempts") from last_error

    def _embed_batch_sync(self, batch: Sequence[str]) -> list[list[float]]:
        result = self.client.models.embed_content(model=self.model, contents=list(batch))
        return [list(item.values) for item in result.embeddings]
```

- [ ] **Step 4: Run embed tests**

Run:

```powershell
cd backend
python -m pytest tests/test_embed.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add data_pipeline/embed.py backend/tests/test_embed.py
git commit -m "add gemini embedding wrapper"
```

---

### Task 5: Add Article And Chunk Models With Alembic

**Files:**
- Create: `backend/app/models/article.py`
- Create: `backend/app/models/chunk.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260525_0001_m1_foundation.py`

- [ ] **Step 1: Create ORM models**

Create `backend/app/models/article.py`:

```python
from sqlalchemy import Column, Date, DateTime, Integer, String, Text, func

from app.database import Base


class Article(Base):
    """A crawled article or legal knowledge base document."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    category = Column(String(50), index=True)
    source = Column(String(150))
    post_date = Column(Date)
    url = Column(Text, unique=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

Create `backend/app/models/chunk.py`:

```python
from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func
from pgvector.sqlalchemy import Vector

from app.database import Base


class Chunk(Base):
    """Semantic retrieval chunk linked to a listing, project, or article."""

    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_type = Column(String(30), nullable=False)
    parent_id = Column(Integer, nullable=False)
    chunk_type = Column(String(50), nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(Vector(768), nullable=False)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_chunks_parent", "parent_type", "parent_id"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
```

Modify `backend/app/models/__init__.py`:

```python
from app.models.article import Article
from app.models.chunk import Chunk
from app.models.chat import ChatMessage, ChatSession
from app.models.listing import Listing
from app.models.project import Project
from app.models.user import User

__all__ = [
    "Article",
    "Chunk",
    "Listing",
    "Project",
    "User",
    "ChatSession",
    "ChatMessage",
]
```

- [ ] **Step 2: Add Alembic config files**

Create `backend/alembic.ini`:

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `backend/alembic/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database import Base
from app.models import Article, ChatMessage, ChatSession, Chunk, Listing, Project, User

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().DATABASE_URL


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `backend/alembic/script.py.mako` using Alembic's default template:

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 3: Add first migration**

Create `backend/alembic/versions/20260525_0001_m1_foundation.py`:

```python
"""m1 foundation schema

Revision ID: 20260525_0001
Revises:
Create Date: 2026-05-25 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision: str = "20260525_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("source", sa.String(length=150), nullable=True),
        sa.Column("post_date", sa.Date(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index(op.f("ix_articles_category"), "articles", ["category"], unique=False)

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_type", sa.String(length=30), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(length=50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=768), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chunks_parent", "chunks", ["parent_type", "parent_id"], unique=False)
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks", postgresql_using="hnsw")
    op.drop_index("ix_chunks_parent", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_articles_category"), table_name="articles")
    op.drop_table("articles")
```

- [ ] **Step 4: Verify metadata imports compile**

Run:

```powershell
python -m compileall backend\app\models backend\alembic
```

Expected: all files compile.

- [ ] **Step 5: Verify migration on local database**

Run local infrastructure if needed:

```powershell
docker-compose up -d postgres
cd backend
alembic upgrade head
```

Expected: migration completes and creates `articles` and `chunks`.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/models/article.py backend/app/models/chunk.py backend/app/models/__init__.py backend/alembic.ini backend/alembic
git commit -m "add m1 vector schema migration"
```

---

### Task 6: Implement Sale Listings Ingestor

**Files:**
- Create: `data_pipeline/ingestors/__init__.py`
- Create: `data_pipeline/ingestors/listings_ingestor.py`
- Modify: `data_pipeline/load_db.py`
- Test: `backend/tests/test_listings_ingestor.py`

- [ ] **Step 1: Write ingestor unit test around row transformation**

Create `backend/tests/test_listings_ingestor.py`:

```python
from data_pipeline.ingestors.listings_ingestor import prepare_listing_chunks


def test_prepare_listing_chunks_pairs_text_and_vectors():
    listing_id = 42
    listing_data = {
        "title": "Bán căn hộ 2PN Quận 7",
        "property_type": "Căn hộ chung cư",
        "listing_type": "sale",
        "price_text": "4,5 tỷ",
        "area_text": "75 m²",
        "district": "Quận 7",
        "city": "Hồ Chí Minh",
        "address": "Phường Tân Phong, Quận 7, Hồ Chí Minh",
        "description": "Gần trường học.",
    }
    vectors = [[0.1] * 768, [0.2] * 768, [0.3] * 768, [0.4] * 768]

    rows = prepare_listing_chunks(listing_id, listing_data, vectors)

    assert rows[0]["parent_type"] == "listing"
    assert rows[0]["parent_id"] == 42
    assert rows[0]["chunk_type"] == "overview"
    assert rows[0]["embedding"] == [0.1] * 768
```

- [ ] **Step 2: Run the test and confirm import failure**

Run:

```powershell
cd backend
python -m pytest tests/test_listings_ingestor.py -q
```

Expected: fail because `data_pipeline.ingestors.listings_ingestor` does not exist.

- [ ] **Step 3: Create ingestor package and helper**

Create empty `data_pipeline/ingestors/__init__.py`.

Create `data_pipeline/ingestors/listings_ingestor.py` with:

```python
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import Base, async_session, engine
from app.models import Chunk, Listing
from data_pipeline.chunk import build_listing_chunks
from data_pipeline.clean import row_to_listing
from data_pipeline.embed import GeminiEmbedder


def read_csv_rows(csv_path: str) -> list[dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def prepare_listing_chunks(
    listing_id: int,
    listing_data: dict[str, Any],
    vectors: list[list[float]],
) -> list[dict[str, Any]]:
    chunks = build_listing_chunks(listing_data)
    if len(chunks) != len(vectors):
        raise ValueError("chunk/vector count mismatch")
    return [
        {
            "parent_type": "listing",
            "parent_id": listing_id,
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "embedding": vector,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
```

- [ ] **Step 4: Add database orchestration**

Append these functions to `listings_ingestor.py`:

```python
async def upsert_listing(session, listing_data: dict[str, Any]) -> Listing:
    product_id = listing_data["product_id"]
    result = await session.execute(select(Listing).where(Listing.product_id == product_id))
    listing = result.scalar_one_or_none()

    if listing is None:
        listing = Listing(**listing_data)
        session.add(listing)
        await session.flush()
        return listing

    for key, value in listing_data.items():
        setattr(listing, key, value)
    await session.flush()
    return listing


async def ingest_listing_rows(rows: list[dict[str, str]], batch_size: int = 50) -> dict[str, int]:
    settings = get_settings()
    embedder = GeminiEmbedder(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_EMBEDDING_MODEL,
        batch_size=100,
    )

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    inserted_or_updated = 0
    chunks_inserted = 0
    errors = 0

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        async with async_session() as session:
            for row in batch:
                try:
                    listing_data = row_to_listing(row)
                    if not listing_data.get("product_id"):
                        continue
                    listing = await upsert_listing(session, listing_data)

                    chunks = build_listing_chunks(listing_data)
                    vectors = await embedder.embed_texts([chunk["text"] for chunk in chunks])
                    chunk_rows = prepare_listing_chunks(listing.id, listing_data, vectors)

                    await session.execute(
                        delete(Chunk).where(
                            Chunk.parent_type == "listing",
                            Chunk.parent_id == listing.id,
                        )
                    )
                    session.add_all([Chunk(**chunk_row) for chunk_row in chunk_rows])
                    inserted_or_updated += 1
                    chunks_inserted += len(chunk_rows)
                except Exception as exc:
                    errors += 1
                    if errors <= 5:
                        print(f"Error on {row.get('product_id', '?')}: {exc}")
            await session.commit()

    return {
        "listings": inserted_or_updated,
        "chunks": chunks_inserted,
        "errors": errors,
    }


async def load_csv_to_db(csv_path: str, batch_size: int = 50) -> dict[str, int]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(csv_path)
    rows = read_csv_rows(csv_path)
    return await ingest_listing_rows(rows, batch_size=batch_size)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest listing CSV into PostgreSQL chunks")
    parser.add_argument("--csv", required=True, help="Path to listing details CSV")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()
    result = await load_csv_to_db(args.csv, args.batch_size)
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Modify old loader to delegate**

Replace `data_pipeline/load_db.py` with a compatibility wrapper:

```python
import asyncio

from data_pipeline.ingestors.listings_ingestor import load_csv_to_db, main


__all__ = ["load_csv_to_db"]


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Run ingestor tests**

Run:

```powershell
cd backend
python -m pytest tests/test_listings_ingestor.py -q
```

Expected: pass.

- [ ] **Step 7: Manual smoke test with a small CSV**

Run after setting `GEMINI_API_KEY` and starting PostgreSQL:

```powershell
docker-compose up -d postgres
python -m data_pipeline.ingestors.listings_ingestor --csv data\listing_details.csv --batch-size 5
```

Expected: command prints a dict containing nonzero `listings` and nonzero `chunks`.

- [ ] **Step 8: Commit**

```powershell
git add data_pipeline/ingestors data_pipeline/load_db.py backend/tests/test_listings_ingestor.py
git commit -m "add listing chunk ingestion pipeline"
```

---

### Task 7: Add Hybrid Search Tool

**Files:**
- Create: `chatbot/tools/__init__.py`
- Create: `chatbot/tools/hybrid_search.py`
- Test: `backend/tests/test_hybrid_search.py`

- [ ] **Step 1: Write filter parsing tests**

Create `backend/tests/test_hybrid_search.py`:

```python
import pytest

from chatbot.tools.hybrid_search import build_listing_filter_clauses, cohere_rerank


def test_build_listing_filter_clauses_maps_supported_filters():
    clauses, params = build_listing_filter_clauses(
        {
            "price_min": 3,
            "price_max": 5,
            "district": "Quận 7",
            "bedrooms": 2,
            "listing_type": "sale",
        }
    )

    sql = " ".join(clauses)

    assert "price >= :price_min" in sql
    assert "price <= :price_max" in sql
    assert "district ILIKE :district" in sql
    assert "bedrooms = :bedrooms" in sql
    assert "listing_type = :listing_type" in sql
    assert params["district"] == "%Quận 7%"


def test_build_listing_filter_clauses_always_filters_active_listings():
    clauses, _ = build_listing_filter_clauses({})
    assert clauses == ["is_active = true"]


@pytest.mark.asyncio
async def test_cohere_rerank_returns_truncated_input_when_api_key_missing(monkeypatch):
    from app import config as app_config

    monkeypatch.setattr(
        app_config,
        "get_settings",
        lambda: type("S", (), {"COHERE_API_KEY": "", "RERANK_MODEL": "x"})(),
    )

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.2},
        {"text": "c", "parent_id": 3, "chunk_type": "overview", "distance": 0.3},
    ]

    result = await cohere_rerank("query", chunks, top_n=2)

    assert result == chunks[:2]


@pytest.mark.asyncio
async def test_cohere_rerank_attaches_score_when_api_succeeds(monkeypatch):
    from app import config as app_config
    from chatbot.tools import hybrid_search as hs

    fake_settings = type(
        "S",
        (),
        {"COHERE_API_KEY": "test-key", "RERANK_MODEL": "rerank-multilingual-v3.0"},
    )()
    monkeypatch.setattr(app_config, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(hs, "get_settings", lambda: fake_settings)

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class FakeAsyncClient:
        def __init__(self, *_, **__):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *_, **__):
            return FakeResponse(
                {"results": [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.4}]}
            )

    monkeypatch.setattr(hs.httpx, "AsyncClient", FakeAsyncClient)

    chunks = [
        {"text": "a", "parent_id": 1, "chunk_type": "overview", "distance": 0.1},
        {"text": "b", "parent_id": 2, "chunk_type": "overview", "distance": 0.2},
    ]

    result = await cohere_rerank("query", chunks, top_n=2)

    assert [chunk["parent_id"] for chunk in result] == [2, 1]
    assert result[0]["rerank_score"] == 0.9
    assert result[1]["rerank_score"] == 0.4
```

- [ ] **Step 2: Run the test and confirm import failure**

Run:

```powershell
cd backend
python -m pytest tests/test_hybrid_search.py -q
```

Expected: fail because `chatbot.tools.hybrid_search` does not exist.

- [ ] **Step 3: Create hybrid search module**

Create empty `chatbot/tools/__init__.py`.

Create `chatbot/tools/hybrid_search.py` with public functions:

```python
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.database import async_session
from data_pipeline.embed import GeminiEmbedder


def build_listing_filter_clauses(filters: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    clauses = ["is_active = true"]
    params: dict[str, Any] = {}

    if filters.get("price_min") is not None:
        clauses.append("price >= :price_min")
        params["price_min"] = filters["price_min"]
    if filters.get("price_max") is not None:
        clauses.append("price <= :price_max")
        params["price_max"] = filters["price_max"]
    if filters.get("district"):
        clauses.append("district ILIKE :district")
        params["district"] = f"%{filters['district']}%"
    if filters.get("city"):
        clauses.append("city ILIKE :city")
        params["city"] = f"%{filters['city']}%"
    if filters.get("bedrooms") is not None:
        clauses.append("bedrooms = :bedrooms")
        params["bedrooms"] = filters["bedrooms"]
    if filters.get("listing_type"):
        clauses.append("listing_type = :listing_type")
        params["listing_type"] = filters["listing_type"]
    if filters.get("property_type"):
        clauses.append("property_type ILIKE :property_type")
        params["property_type"] = f"%{filters['property_type']}%"

    return clauses, params
```

- [ ] **Step 4: Add async search stages**

Append to `hybrid_search.py`:

```python
async def sql_filter(parent_type: str, filters: dict[str, Any], limit: int = 500) -> list[int]:
    if parent_type != "listing":
        return []

    clauses, params = build_listing_filter_clauses(filters)
    params["limit"] = limit
    query = text(
        "SELECT id FROM listings "
        f"WHERE {' AND '.join(clauses)} "
        "ORDER BY updated_at DESC NULLS LAST, id DESC "
        "LIMIT :limit"
    )
    async with async_session() as session:
        result = await session.execute(query, params)
        return [row[0] for row in result.all()]


async def pgvector_knn(
    query_embedding: list[float],
    parent_type: str,
    parent_ids: list[int],
    k: int,
) -> list[dict[str, Any]]:
    if not parent_ids:
        return []

    query = text(
        "SELECT id, parent_type, parent_id, chunk_type, text, "
        "embedding <=> CAST(:query_embedding AS vector) AS distance "
        "FROM chunks "
        "WHERE parent_type = :parent_type AND parent_id = ANY(:parent_ids) "
        "ORDER BY embedding <=> CAST(:query_embedding AS vector) "
        "LIMIT :k"
    )
    params = {
        "query_embedding": str(query_embedding),
        "parent_type": parent_type,
        "parent_ids": parent_ids,
        "k": k,
    }
    async with async_session() as session:
        result = await session.execute(query, params)
        return [dict(row._mapping) for row in result.all()]


async def cohere_rerank(query: str, chunks: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    settings = get_settings()
    if not chunks or not settings.COHERE_API_KEY:
        return chunks[:top_n]

    payload = {
        "model": settings.RERANK_MODEL,
        "query": query,
        "documents": [chunk["text"] for chunk in chunks],
        "top_n": top_n,
    }
    headers = {
        "Authorization": f"Bearer {settings.COHERE_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.cohere.com/v2/rerank", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    reranked = []
    for item in data.get("results", []):
        chunk = dict(chunks[item["index"]])
        chunk["rerank_score"] = item.get("relevance_score")
        reranked.append(chunk)
    return reranked


async def resolve_to_listing_records(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent_ids = []
    for chunk in chunks:
        parent_id = chunk["parent_id"]
        if parent_id not in parent_ids:
            parent_ids.append(parent_id)

    if not parent_ids:
        return []

    query = text(
        "SELECT id, product_id, title, price, price_text, area, area_text, bedrooms, "
        "bathrooms, district, city, address, url "
        "FROM listings WHERE id = ANY(:ids)"
    )
    async with async_session() as session:
        result = await session.execute(query, {"ids": parent_ids})
        listings = {row._mapping["id"]: dict(row._mapping) for row in result.all()}

    records: list[dict[str, Any]] = []
    for chunk in chunks:
        listing = listings.get(chunk["parent_id"])
        if not listing:
            continue
        if any(record["id"] == listing["id"] for record in records):
            continue
        listing["matched_chunk"] = {
            "chunk_type": chunk["chunk_type"],
            "text": chunk["text"],
            "distance": float(chunk["distance"]),
            "rerank_score": chunk.get("rerank_score"),
        }
        records.append(listing)
    return records


async def hybrid_search(
    query: str,
    filters: dict[str, Any] | None = None,
    parent_type: str = "listing",
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict[str, Any]]:
    filters = filters or {}
    candidate_ids = await sql_filter(parent_type, filters)
    if not candidate_ids:
        return []

    settings = get_settings()
    embedder = GeminiEmbedder(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_EMBEDDING_MODEL,
        batch_size=1,
    )
    query_embedding = (await embedder.embed_texts([query]))[0]
    chunks = await pgvector_knn(query_embedding, parent_type=parent_type, parent_ids=candidate_ids, k=top_k)
    reranked = await cohere_rerank(query, chunks, top_n=rerank_to)

    if parent_type == "listing":
        return await resolve_to_listing_records(reranked)
    return []
```

- [ ] **Step 5: Run hybrid search unit test**

Run:

```powershell
cd backend
python -m pytest tests/test_hybrid_search.py -q
```

Expected: pass.

- [ ] **Step 6: Manual search smoke test**

Run after ingesting at least one listing:

```powershell
python -m chatbot.tools.hybrid_search --query "căn hộ 2PN Quận 7 dưới 5 tỷ"
```

If no CLI exists yet, add this to the bottom of `hybrid_search.py`:

```python
if __name__ == "__main__":
    import argparse
    import asyncio
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(hybrid_search(args.query)), ensure_ascii=False, indent=2, default=str))
```

Expected: JSON list of up to 5 listing records with `matched_chunk`.

- [ ] **Step 7: Commit**

```powershell
git add chatbot/tools backend/tests/test_hybrid_search.py
git commit -m "add hybrid listing search tool"
```

---

### Task 8: Wire Property Search Agent To Hybrid Search

**Files:**
- Modify: `chatbot/agents/property_search.py`

LangGraph supports async node functions when the graph is invoked via `ainvoke`. `chatbot/graph.py:187` already calls `chat_graph.ainvoke(initial_state)`, so converting one node to `async def` is safe even while sibling nodes stay synchronous. Step 1 verifies that assumption before any code change; Step 2 makes the conversion.

- [ ] **Step 1: Verify the graph runs async nodes**

Run a quick probe to confirm async nodes work in the existing compiled graph:

```powershell
python -c "from chatbot.graph import chat_graph; print(chat_graph.get_graph().nodes)"
```

Expected: nodes list prints without errors. If the command errors, stop and resolve the import first — do not proceed with the async conversion until the graph imports cleanly.

- [ ] **Step 2: Convert node to async and call hybrid_search**

Replace `property_search_node` in `chatbot/agents/property_search.py`:

```python
from chatbot.tools.hybrid_search import hybrid_search


async def property_search_node(state: ChatState) -> dict:
    query = state.get("user_query", "")
    filters = state.get("search_filters", {})
    listings = await hybrid_search(query=query, filters=filters, parent_type="listing")
    listings_text = format_listing_results(listings)
    response_text = PROPERTY_PROMPT.format(
        query=query,
        filters=filters if filters else "Không có bộ lọc cụ thể",
        count=len(listings),
        listings_text=listings_text,
    )

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "property_search": {
                "agent_name": "property_search",
                "content": response_text,
                "sources": [item.get("url") for item in listings if item.get("url")],
                "confidence": 0.85 if listings else 0.35,
            },
        },
    }
```

Add helper:

```python
def format_listing_results(listings: list[dict]) -> str:
    if not listings:
        return "Không tìm thấy bất động sản phù hợp trong dữ liệu hiện có."

    lines = []
    for index, item in enumerate(listings, start=1):
        lines.append(
            f"{index}. {item.get('title') or 'Không có tiêu đề'} | "
            f"{item.get('price_text') or item.get('price') or 'Chưa rõ giá'} | "
            f"{item.get('area_text') or item.get('area') or 'Chưa rõ diện tích'} | "
            f"{item.get('district') or ''}, {item.get('city') or ''} | "
            f"{item.get('url') or ''}"
        )
    return "\n".join(lines)
```

- [ ] **Step 2: Compile chatbot package**

Run:

```powershell
python -m compileall chatbot
```

Expected: all files compile.

- [ ] **Step 3: Run backend import smoke test**

Run:

```powershell
python -c "import chatbot.agents.property_search as p; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 4: Commit**

```powershell
git add chatbot/agents/property_search.py
git commit -m "wire property agent to hybrid search"
```

---

### Task 9: Sale Crawler Refactor Preparation

**Files:**
- Create: `crawler/__init__.py`
- Create: `crawler/core/__init__.py`
- Create: `crawler/core/csv_writer.py`
- Create: `crawler/core/parser.py`
- Create: `crawler/sale/__init__.py`
- Create: `crawler/sale/crawl_urls.py`
- Create: `crawler/sale/crawl_details.py`
- Test: `backend/tests/test_crawler_core.py`

- [ ] **Step 1: Write failing tests for crawler core helpers**

Create `backend/tests/test_crawler_core.py`:

```python
import csv
from pathlib import Path

from crawler.core.csv_writer import append_csv, merge_tmp_files, read_done_ids


FIELDNAMES = ["product_id", "url"]


def test_append_csv_writes_header_once(tmp_path: Path):
    target = tmp_path / "out.csv"

    append_csv(str(target), [{"product_id": "1", "url": "u1"}], FIELDNAMES)
    append_csv(str(target), [{"product_id": "2", "url": "u2"}], FIELDNAMES)

    rows = list(csv.DictReader(target.open(encoding="utf-8-sig")))
    assert [row["product_id"] for row in rows] == ["1", "2"]


def test_append_csv_skips_empty_input(tmp_path: Path):
    target = tmp_path / "out.csv"

    append_csv(str(target), [], FIELDNAMES)

    assert not target.exists()


def test_read_done_ids_returns_existing_keys(tmp_path: Path):
    target = tmp_path / "out.csv"
    append_csv(str(target), [{"product_id": "a", "url": "ua"}, {"product_id": "b", "url": "ub"}], FIELDNAMES)

    assert read_done_ids(str(target)) == {"a", "b"}


def test_merge_tmp_files_deduplicates_by_product_id(tmp_path: Path):
    output = tmp_path / "merged.csv"
    worker_a = tmp_path / "merged.csv.worker0.tmp"
    worker_b = tmp_path / "merged.csv.worker1.tmp"
    append_csv(str(worker_a), [{"product_id": "1", "url": "u1"}, {"product_id": "2", "url": "u2"}], FIELDNAMES)
    append_csv(str(worker_b), [{"product_id": "2", "url": "u2-dup"}, {"product_id": "3", "url": "u3"}], FIELDNAMES)

    count = merge_tmp_files(str(tmp_path / "merged.csv.worker*.tmp"), str(output), FIELDNAMES)

    rows = list(csv.DictReader(output.open(encoding="utf-8-sig")))
    assert count == 3
    assert sorted(row["product_id"] for row in rows) == ["1", "2", "3"]
```

- [ ] **Step 2: Run the test and confirm import failure**

Run:

```powershell
cd backend
python -m pytest tests/test_crawler_core.py -q
```

Expected: fail because `crawler.core.csv_writer` does not exist.

- [ ] **Step 3: Extract CSV helpers**

Create `crawler/__init__.py`, `crawler/core/__init__.py`, and `crawler/core/csv_writer.py` by moving CSV helper behavior from `Crawl/01.crawl_listing_url.py` and `Crawl/02.crawl_listing_details.py`:

```python
from __future__ import annotations

import csv
import glob
import os


def append_csv(path: str, rows: list[dict], fieldnames: list[str]) -> None:
    if not rows:
        return
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def read_done_ids(output: str, key: str = "product_id") -> set[str]:
    if not os.path.exists(output):
        return set()
    with open(output, newline="", encoding="utf-8-sig") as handle:
        return {row[key] for row in csv.DictReader(handle) if row.get(key)}


def merge_tmp_files(pattern: str, output: str, fieldnames: list[str], dedupe_key: str = "product_id") -> int:
    rows: list[dict] = []
    for path in glob.glob(pattern):
        with open(path, newline="", encoding="utf-8-sig") as handle:
            rows.extend(csv.DictReader(handle))

    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        key = row.get(dedupe_key)
        if key and key not in seen:
            seen.add(key)
            deduped.append(row)

    with open(output, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(deduped)
    return len(deduped)
```

- [ ] **Step 4: Run crawler core tests**

Run:

```powershell
cd backend
python -m pytest tests/test_crawler_core.py -q
```

Expected: pass.

- [ ] **Step 5: Extract text helper**

Create `crawler/core/parser.py`:

```python
def text_or_empty(element) -> str:
    if element is None:
        return ""
    try:
        return " ".join(element.inner_text().split())
    except Exception:
        return ""
```

- [ ] **Step 6: Copy sale crawler entrypoints**

Create `crawler/sale/__init__.py`, `crawler/sale/crawl_urls.py`, and `crawler/sale/crawl_details.py` by copying the existing behavior from:

- `Crawl/01.crawl_listing_url.py`
- `Crawl/02.crawl_listing_details.py`

Then replace local helper calls:

```python
from crawler.core.csv_writer import append_csv, merge_tmp_files, read_done_ids
from crawler.core.parser import text_or_empty
```

Keep the default sale URL:

```python
BASE_URL = "https://batdongsan.com.vn/nha-dat-ban"
```

- [ ] **Step 7: Add incremental flag**

In both sale entrypoints, add:

```python
parser.add_argument("--since", default=None, help="Only keep rows with post_date >= YYYY-MM-DD when post_date is available")
```

For M1, apply `--since` only in `crawl_details.py` after parsing detail rows. If a row has no parseable `post_date`, keep it so the crawler does not silently drop usable listings.

- [ ] **Step 8: Compile crawler modules**

Run:

```powershell
python -m compileall crawler
```

Expected: all files compile.

- [ ] **Step 9: Manual crawler smoke test**

Run:

```powershell
python -m crawler.sale.crawl_urls --pages 1 1 --output data\raw\sale_urls_test.csv
```

Expected: output CSV exists with `product_id` and `url` columns. Exact row count depends on batdongsan.com availability and bot detection.

- [ ] **Step 10: Commit**

```powershell
git add crawler backend/tests/test_crawler_core.py
git commit -m "refactor sale crawler into package"
```

---

### Task 10: M1 End-To-End Verification

**Files:**
- No required code changes unless a previous task failed verification.

- [ ] **Step 1: Compile Python modules**

Run:

```powershell
python -m compileall backend\app chatbot data_pipeline crawler
```

Expected: all modules compile.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
cd backend
python -m pytest tests/test_pipeline_config.py tests/test_clean.py tests/test_chunk.py tests/test_embed.py tests/test_listings_ingestor.py tests/test_hybrid_search.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Start PostgreSQL**

Run:

```powershell
docker-compose up -d postgres
```

Expected: `realestate_postgres` becomes healthy.

- [ ] **Step 4: Apply migration**

Run:

```powershell
cd backend
alembic upgrade head
```

Expected: revision `20260525_0001` applied.

- [ ] **Step 5: Ingest a tiny sale batch**

Run from repo root after setting `GEMINI_API_KEY`:

```powershell
python -m data_pipeline.ingestors.listings_ingestor --csv data\listing_details.csv --batch-size 5
```

Expected: printed result contains nonzero `listings` and `chunks`.

- [ ] **Step 6: Run hybrid search**

Run:

```powershell
python -m chatbot.tools.hybrid_search --query "căn hộ 2PN Quận 7 dưới 5 tỷ"
```

Expected: JSON output contains up to 5 listing records with `matched_chunk.text`.

- [ ] **Step 7: Backend chat smoke test**

Run:

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

In another shell:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/chat -ContentType "application/json" -Body '{"message":"Tìm căn hộ 2PN Quận 7 dưới 5 tỷ"}'
```

Expected: response uses `property_search` path and includes listing-oriented content. If the current chat router still wraps the old sync graph, record that as a follow-up for the chatbot integration milestone; M1 is still valid if `hybrid_search.py` works directly.

- [ ] **Step 8: Commit verification fixes**

If any verification step required code changes:

```powershell
git add <changed-files>
git commit -m "fix m1 verification issues"
```

---

## Self-Review

- Spec coverage: M1 covers test path setup (Task 0), config defaults (Task 1), parser extraction (Task 2), semantic chunking (Task 3), Gemini embeddings (Task 4), `articles`/`chunks` schema with Alembic (Task 5), listing ingestion (Task 6), hybrid retrieval with rerank fallback (Task 7), property agent wiring (Task 8), sale crawler refactor with core helpers tested (Task 9), and end-to-end verification (Task 10). M2 covers rent/projects/news crawlers and `data_pipeline/enrich.py` (geocoding + LLM intent extraction). M3 covers Airflow. M4 covers legal PDF ingestion. M5 covers monitoring, performance polish, and dropping the now-unused `Listing.embedding` column.
- Placeholder scan: every implementation step lists concrete functions/classes and runnable verification commands. The Cohere v2 schema note in the scope section makes the only external-dependency assumption explicit.
- Type consistency: chunks use `dict[str, Any]` in pipeline helpers and ORM `Chunk` rows with `parent_type`, `parent_id`, `chunk_type`, `text`, and `embedding`; hybrid search resolves listing records using the same `parent_type="listing"` convention.
- Known limits accepted in M1: `latitude`/`longitude` stay NULL until M2 ships geocoding; `Listing.embedding` is dormant until a later migration drops it; `cohere_rerank` falls back to vector-distance ordering when `COHERE_API_KEY` is unset.
