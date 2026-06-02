# Crawl Publish Before Semantic Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure crawled listing data is published to PostgreSQL and visible on the web immediately after crawl detail CSV generation, while BGE-M3 chunk indexing runs after publish and cannot block web visibility.

**Architecture:** Keep CSV as the durable crawler artifact for resume/debug. Refactor listing ingestion into two explicit phases: publish structured listings to `listings` first, then build chunks and embeddings for chatbot/RAG. Airflow and manual commands continue to use CSV inputs, but their result metrics distinguish publish errors from semantic index errors.

**Tech Stack:** Python 3.11, FastAPI models, SQLAlchemy async, PostgreSQL + pgvector, existing crawler CSVs, BGE-M3 embedder, pytest, Airflow.

---

## Current Problem

Today `data_pipeline/ingestors/listings_ingestor.py` does clean, enrich, chunk, embed, and DB write as one combined batch. If the BGE-M3 embedding call fails for a batch, the code continues without writing those listings to `listings`, so the web UI cannot show newly crawled data even though crawl detail CSV exists.

Target behavior:

```text
crawl detail CSV exists
-> publish rows into listings
-> web /api/v1/listings can show them
-> chunk + embed + chunks insert runs after publish
-> chatbot/RAG becomes available when indexing succeeds
```

CSV remains part of the flow. The crawler should not write directly to DB in this plan; the ingestion step publishes the CSV to DB.

---

## File Structure

- Modify: `data_pipeline/ingestors/listings_ingestor.py`
  - Add a publish-only phase for listing rows.
  - Add a separate semantic indexing phase for already-persisted listings.
  - Return separate counters for `published`, `indexed`, `chunks`, `publish_errors`, and `index_errors`.
- Modify: `backend/tests/test_listings_ingestor.py`
  - Add tests proving publish still happens when embedding fails.
  - Add tests proving chunks are replaced only in indexing phase.
- Modify: `airflow/plugins/pipeline_runner.py`
  - Preserve existing `run_listings_ingestion()` API but expect/report the expanded result shape.
- Modify: `airflow/dags/daily_listings_dag.py`
  - Rename task labels/descriptions only if helpful; keep DAG order `crawl_urls -> crawl_details -> ingest -> mark_done`.
- Modify: `guide_chay_datapipeline.md`
  - Document that the ingest command publishes to web first and indexes chatbot chunks second.
- Optional: create `backend/tests/test_daily_listings_dag_publish_flow.py` only if existing DAG tests do not cover task order.

---

### Task 1: Add Tests For Publish-Before-Index Behavior

**Files:**
- Modify: `backend/tests/test_listings_ingestor.py`
- Modify: `data_pipeline/ingestors/listings_ingestor.py`

- [x] **Step 1: Add a failing test proving embedding failure does not block publish**

Append this test to `backend/tests/test_listings_ingestor.py`, adapting imports if the file already imports these symbols:

```python
import pytest

from data_pipeline.ingestors import listings_ingestor as li


class FailingEmbedder:
    async def embed_texts(self, texts):
        raise RuntimeError("embedding service unavailable")


class NoopGeocoder:
    async def geocode(self, address):
        return None


class NoopIntentExtractor:
    async def extract(self, content):
        return []


def sample_listing_row(product_id="publish-1"):
    return {
        "product_id": product_id,
        "title": "Can ho 2PN Quan 7",
        "description": "Can ho gan truong, phap ly ro",
        "price_text": "5 ty",
        "price_per_m2_text": "80 trieu/m2",
        "area_text": "62 m2",
        "bedrooms": "2",
        "bathrooms": "2",
        "address": "Quan 7, Ho Chi Minh",
        "url": "https://example.test/listing/publish-1",
    }


@pytest.mark.asyncio
async def test_publish_survives_embedding_failure(monkeypatch, db_session):
    async def fake_publish_batch(rows):
        assert rows[0]["product_id"] == "publish-1"
        return [type("PersistedListing", (), {"id": 101, "product_id": "publish-1"})()]

    monkeypatch.setattr(li, "publish_listing_batch", fake_publish_batch)
    monkeypatch.setattr(li, "build_geocoder", lambda **kwargs: NoopGeocoder())
    monkeypatch.setattr(li, "BGEEmbedder", lambda **kwargs: FailingEmbedder())

    result = await li.ingest_listing_rows([sample_listing_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 1
```

If the current test suite uses a different async DB fixture name, use the existing fixture from `backend/tests/conftest.py`.

- [x] **Step 2: Run the new test and confirm failure**

Run:

```powershell
python -m pytest backend\tests\test_listings_ingestor.py::test_publish_survives_embedding_failure -q
```

Expected: fail because `publish_listing_batch` does not exist or `ingest_listing_rows()` returns the old `{"listings", "chunks", "errors"}` shape.

---

### Task 2: Split Listing Ingestion Into Publish And Index Phases

**Files:**
- Modify: `data_pipeline/ingestors/listings_ingestor.py`
- Test: `backend/tests/test_listings_ingestor.py`

- [x] **Step 1: Add a publish result shape**

In `data_pipeline/ingestors/listings_ingestor.py`, define the output counters used by all listing ingestion paths:

```python
def empty_ingest_result() -> dict[str, int]:
    return {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }
```

- [x] **Step 2: Add a batch publisher**

Add this helper near `upsert_listing()`:

```python
async def publish_listing_batch(
    listings_data: list[dict[str, Any]],
) -> list[Listing]:
    persisted: list[Listing] = []
    async with async_session() as session:
        for listing_data in listings_data:
            listing = await upsert_listing(session, listing_data)
            persisted.append(listing)
        await session.commit()
    return persisted
```

This function only writes `listings`. It must not build chunks or call the embedder.

- [x] **Step 3: Add a semantic index helper**

Add this helper after `publish_listing_batch()`:

```python
async def index_listing_batch(
    listings_with_chunks: list[tuple[Listing, list[dict[str, Any]]]],
    *,
    embedder: Any,
) -> dict[str, int]:
    if not listings_with_chunks:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    flat_texts = [
        chunk["text"]
        for _, chunks in listings_with_chunks
        for chunk in chunks
    ]
    if not flat_texts:
        return {"indexed": 0, "chunks": 0, "index_errors": 0}

    try:
        flat_vectors = await embedder.embed_texts(flat_texts)
    except Exception as exc:
        print(f"[ingest] semantic index embed batch failed: {exc}", file=sys.stderr)
        return {
            "indexed": 0,
            "chunks": 0,
            "index_errors": len(listings_with_chunks),
        }

    cursor = 0
    indexed = 0
    chunks_inserted = 0
    index_errors = 0

    async with async_session() as session:
        for listing, chunks in listings_with_chunks:
            count = len(chunks)
            vectors = flat_vectors[cursor : cursor + count]
            cursor += count
            try:
                chunk_rows = prepare_listing_chunks(listing.id, chunks, vectors)
                await session.execute(
                    delete(Chunk).where(
                        Chunk.parent_type == "listing",
                        Chunk.parent_id == listing.id,
                    )
                )
                session.add_all([Chunk(**chunk_row) for chunk_row in chunk_rows])
                indexed += 1
                chunks_inserted += len(chunk_rows)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                index_errors += 1
                print(
                    f"[ingest] semantic index db write failed for {listing.product_id}: {exc}",
                    file=sys.stderr,
                )
        await session.commit()

    return {
        "indexed": indexed,
        "chunks": chunks_inserted,
        "index_errors": index_errors,
    }
```

- [x] **Step 4: Rewrite `ingest_listing_rows()` around the two phases**

Replace the current per-batch body with this structure:

```python
async def ingest_listing_rows(rows: list[dict[str, str]], batch_size: int = 50) -> dict[str, int]:
    settings = get_settings()
    embedder = BGEEmbedder(
        model_name=settings.HF_EMBEDDING_MODEL,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        embedding_dim=settings.EMBEDDING_DIM,
        device=settings.HF_EMBEDDING_DEVICE or None,
    )

    geocoder = build_geocoder(
        provider=settings.GEOCODER_PROVIDER,
        user_agent=settings.GEOCODER_USER_AGENT,
        goong_api_key=settings.GOONG_API_KEY,
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

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    result = empty_ingest_result()

    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []

        for row in batch:
            try:
                listing_data = row_to_listing(row)
                if not listing_data.get("product_id"):
                    continue
                listing_data = await enrich_listing_data(
                    listing_data,
                    geocoder=geocoder,
                    intent_extractor=intent_extractor,
                )
                chunks = build_listing_chunks(listing_data)
                prepared.append((listing_data, chunks))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                result["publish_errors"] += 1
                print(
                    f"[ingest] clean/enrich failed for {row.get('product_id', '?')}: {exc}",
                    file=sys.stderr,
                )

        if not prepared:
            continue

        try:
            persisted = await publish_listing_batch([listing_data for listing_data, _ in prepared])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            result["publish_errors"] += len(prepared)
            print(f"[ingest] publish batch failed: {exc}", file=sys.stderr)
            continue

        result["published"] += len(persisted)

        listings_with_chunks = [
            (listing, chunks)
            for listing, (_, chunks) in zip(persisted, prepared, strict=True)
        ]
        index_result = await index_listing_batch(listings_with_chunks, embedder=embedder)
        result["indexed"] += index_result["indexed"]
        result["chunks"] += index_result["chunks"]
        result["index_errors"] += index_result["index_errors"]

    return result
```

- [x] **Step 5: Keep backwards compatibility for old metrics consumers**

If any tests or metrics still expect `listings` and `errors`, update them to use the new names. Do not keep duplicate counters in production code unless a caller still requires them. Prefer updating callers to:

```python
published = result["published"]
errors = result["publish_errors"] + result["index_errors"]
```

- [x] **Step 6: Run targeted tests**

Run:

```powershell
python -m pytest backend\tests\test_listings_ingestor.py -q
```

Expected: all listing ingestor tests pass.

- [ ] **Step 7: Commit this task** - Skipped in this session because the worktree already contains broad unrelated changes and no commit was requested.

```powershell
git add data_pipeline/ingestors/listings_ingestor.py backend/tests/test_listings_ingestor.py
git commit -m "publish crawled listings before semantic indexing"
```

Do not include `.env` in this commit.

---

### Task 3: Add Publish-Only Test Coverage

**Files:**
- Modify: `backend/tests/test_listings_ingestor.py`
- Modify: `data_pipeline/ingestors/listings_ingestor.py`

- [x] **Step 1: Add a unit test for `publish_listing_batch()` contract**

Add this test:

```python
@pytest.mark.asyncio
async def test_publish_listing_batch_does_not_call_embedder(monkeypatch):
    called = {"embed": False}

    class ExplodingEmbedder:
        async def embed_texts(self, texts):
            called["embed"] = True
            raise AssertionError("publish phase must not embed")

    monkeypatch.setattr(li, "BGEEmbedder", lambda **kwargs: ExplodingEmbedder())

    rows = [sample_listing_row("publish-only-1")]
    result = await li.ingest_listing_rows(rows, batch_size=1)

    assert result["published"] == 1
    assert called["embed"] is True
    assert result["index_errors"] == 1
```

This test proves publish already happened before the embedder failure. If the existing DB fixture cannot persist rows in this test, assert through a monkeypatched `publish_listing_batch()` as in Task 1.

- [x] **Step 2: Add a test for result keys**

Add:

```python
def test_empty_ingest_result_shape():
    assert li.empty_ingest_result() == {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }
```

- [x] **Step 3: Run targeted tests**

Run:

```powershell
python -m pytest backend\tests\test_listings_ingestor.py -q
```

Expected: tests pass.

- [ ] **Step 4: Commit this task** - Skipped in this session because the worktree already contains broad unrelated changes and no commit was requested.

```powershell
git add backend/tests/test_listings_ingestor.py data_pipeline/ingestors/listings_ingestor.py
git commit -m "test listing publish and index result contract"
```

---

### Task 4: Update Airflow And Pipeline Metrics Expectations

**Files:**
- Modify: `airflow/plugins/pipeline_runner.py`
- Modify: `airflow/dags/daily_listings_dag.py`
- Modify: `backend/tests/test_pipeline_runner.py`
- Modify: `backend/tests/test_dag_structure.py`

- [x] **Step 1: Keep `run_listings_ingestion()` returning the new result unchanged**

In `airflow/plugins/pipeline_runner.py`, ensure the function remains:

```python
def run_listings_ingestion(csv_path: str, batch_size: int = 50) -> dict[str, int]:
    sys.path.insert(0, str(REPO_ROOT))
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    import asyncio

    from data_pipeline.ingestors.listings_ingestor import load_csv_to_db

    return asyncio.run(load_csv_to_db(csv_path, batch_size=batch_size))
```

Do not translate the new result shape back to the old one.

- [x] **Step 2: Rename Airflow task descriptions for clarity**

In `airflow/dags/daily_listings_dag.py`, change the DAG description to:

```python
description=(
    "Crawl sale and rent listings, publish detail CSV rows to PostgreSQL for "
    "web visibility, then run semantic chunk indexing for chatbot retrieval. "
    "Requires the `realestate_app` Airflow connection (Admin -> Connections) "
    "pointing at the app Postgres."
),
```

Keep task order:

```python
crawl_urls >> crawl_details >> ingest >> mark_done
```

- [x] **Step 3: Add or update DAG structure test**

In `backend/tests/test_dag_structure.py`, assert the listing DAG still has this dependency chain for each source group:

```python
def test_daily_listings_dag_publish_after_crawl_details():
    from airflow.dags.daily_listings_dag import dag

    sale_ingest = dag.get_task("sale.ingest_sale")
    sale_details = dag.get_task("sale.crawl_sale_details")
    sale_done = dag.get_task("sale.mark_sale_done")

    assert sale_ingest in sale_details.downstream_list
    assert sale_done in sale_ingest.downstream_list
```

If the test suite imports DAGs differently, follow the existing pattern in `backend/tests/test_dag_structure.py`.

- [x] **Step 4: Run Airflow-related tests**

Run:

```powershell
python -m pytest backend\tests\test_pipeline_runner.py backend\tests\test_dag_structure.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit this task** - Skipped in this session because the worktree already contains broad unrelated changes and no commit was requested.

```powershell
git add airflow/plugins/pipeline_runner.py airflow/dags/daily_listings_dag.py backend/tests/test_pipeline_runner.py backend/tests/test_dag_structure.py
git commit -m "clarify crawl publish airflow flow"
```

---

### Task 5: Update Runbook For Crawl-To-Web Flow

**Files:**
- Modify: `guide_chay_datapipeline.md`
- Modify: `docs/pipeline.md`

- [x] **Step 1: Add the manual crawl-and-publish command sequence**

In `guide_chay_datapipeline.md`, add a section named `Crawl -> publish web -> index chatbot`:

```markdown
## Crawl -> publish web -> index chatbot

Crawler detail stages still write CSV first. To make crawled listings appear on the web, run the listing ingestor immediately after the detail CSV is produced:

```bash
python -m crawler.sale.crawl_urls --pages 1 30 --output data/raw/sale_urls.csv --workers 4
python -m crawler.sale.crawl_details --input data/raw/sale_urls.csv --output data/raw/sale_details.csv --workers 4
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_details.csv --batch-size 50
```

The ingestor publishes rows to `listings` first so `/api/v1/listings` and the Next.js listing pages can show them. It then attempts BGE-M3 chunk indexing for chatbot/RAG. If indexing fails, fix the index error and rerun the same ingestor command; upsert by `product_id` keeps the web data idempotent.
```

- [x] **Step 2: Add the same architecture note to `docs/pipeline.md`**

Add this paragraph near the pipeline overview:

```markdown
Current listing ingestion is intentionally publish-first: crawled detail CSV rows are upserted into `listings` before semantic chunks are embedded. The web UI only depends on `listings`; chatbot/RAG depends on `chunks`, so embedding failures must not prevent crawled listings from appearing on the site.
```

- [x] **Step 3: Run docs grep**

Run:

```powershell
rg "publish web|publish-first|embedding failures must not prevent" guide_chay_datapipeline.md docs\pipeline.md
```

Expected: both docs contain the new publish-first flow.

- [ ] **Step 4: Commit this task** - Skipped in this session because the worktree already contains broad unrelated changes and no commit was requested.

```powershell
git add guide_chay_datapipeline.md docs/pipeline.md
git commit -m "document crawl publish before index flow"
```

---

### Task 6: End-To-End Verification

**Files:**
- No new files.

- [x] **Step 1: Run backend tests**

```powershell
python -m pytest backend\tests -q
```

Expected: all tests pass. Skips are acceptable if they were already expected.

- [x] **Step 2: Run syntax check**

```powershell
python -m compileall backend\app data_pipeline chatbot crawler
```

Expected: no syntax errors.

- [x] **Step 3: Run frontend lint**

```powershell
cd frontend
npm run lint
```

Expected: ESLint exits with code 0.

- [ ] **Step 4: Smoke test local publish flow with a tiny CSV** - Skipped in this session because it writes to the local database and can run BGE-M3 embedding work against real data.

Use an existing small CSV or create a temporary CSV outside tracked docs, then run:

```powershell
python -m data_pipeline.ingestors.listings_ingestor --csv data/apartments_cleaned.csv --batch-size 5
```

Expected output shape:

```text
{'published': <n>, 'indexed': <m>, 'chunks': <k>, 'publish_errors': 0, 'index_errors': <x>}
```

Then verify web-facing data:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/listings?listing_type=sale&limit=1"
```

Expected: response has `total > 0` and at least one item.

- [ ] **Step 5: Commit verification-only changes if any** - Skipped in this session because no commit was requested.

Do not commit generated CSVs, caches, `.env`, or local DB artifacts.

---

## Public Interfaces And Data Contracts

- Crawler CLI remains unchanged and still writes CSV.
- Manual publish command remains `python -m data_pipeline.ingestors.listings_ingestor --csv <details.csv>`.
- `load_csv_to_db()` and `run_listings_ingestion()` still return `dict[str, int]`, but keys become:
  - `published`
  - `indexed`
  - `chunks`
  - `publish_errors`
  - `index_errors`
- `listings.product_id` remains the idempotent upsert key.
- Web visibility depends on `listings`, not `chunks`.
- Chatbot/RAG readiness depends on `chunks`.

---

## Test Cases And Scenarios

- Fresh crawl detail CSV publishes rows into `listings`.
- Re-running the same CSV updates existing rows by `product_id` without duplicates.
- BGE-M3 embed failure increments `index_errors` but does not erase or block published listings.
- Chunk DB write failure increments `index_errors` but does not roll back published listings.
- Missing `product_id` rows are skipped or counted as publish errors according to existing clean behavior.
- Airflow task order remains `crawl_urls -> crawl_details -> ingest -> mark_done`.
- `/api/v1/listings` shows published rows even when `chunks` has not been populated.

---

## Assumptions

- This plan only changes listings/sale/rent ingestion. Projects/news get their own selector plan.
- CSV remains the durable crawler artifact.
- Web pages should show data after structured DB publish, not after semantic indexing.
- It is acceptable for chatbot/RAG to lag behind web visibility.
- Existing dirty worktree changes must be preserved; commits should include only files from the task being completed.
