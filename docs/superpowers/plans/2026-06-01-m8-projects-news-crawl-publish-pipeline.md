# Projects And News Crawl Publish Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement real projects/news crawler selectors and make their crawled CSV output follow the same unified publish-before-index flow as listings: CSV first, structured DB rows visible to web/API second, semantic chunks for chatbot third.

**Architecture:** Keep crawler CLI contracts and CSV artifacts unchanged. Add fixture-backed parser tests for projects/news, then refactor projects/news ingestion to publish structured parent records before BGE-M3 chunk indexing. This plan extends the listing-focused `2026-06-01-m7-crawl-publish-before-index.md` pattern to `projects` and `articles` so all content sources share one pipeline contract.

**Tech Stack:** Python 3.11, Playwright crawler modules, existing CSV writer/parser helpers, SQLAlchemy async, PostgreSQL + pgvector, BGE-M3 embedder, pytest, Airflow.

---

## Unified Flow

All crawlable sources should follow one shape:

```text
crawl URLs/articles/details
-> write CSV artifact for resume/debug/audit
-> publish structured parent rows into PostgreSQL
   - listings -> listings
   - projects -> projects
   - news/legal -> articles
-> web/API can read parent rows without waiting for embeddings
-> build semantic chunks + BGE-M3 vectors
-> insert/replace rows in chunks for chatbot/RAG
```

This plan must not make crawler code write directly to PostgreSQL. Crawlers write CSV. Ingestors publish CSV rows to DB. Semantic indexing must not block parent rows from becoming visible to the web/API.

Related plan:

- `docs/superpowers/plans/2026-06-01-m7-crawl-publish-before-index.md` handles listings/sale/rent.
- This plan handles projects/news selectors and applies the same publish-before-index contract to `projects_ingestor.py` and `news_ingestor.py`.

---

## File Structure

- Create: `backend/tests/fixtures/project_listing_sample.html`
- Create: `backend/tests/fixtures/project_detail_sample.html`
- Create: `backend/tests/fixtures/news_listing_sample.html`
- Create: `backend/tests/fixtures/news_article_sample.html`
- Create: `backend/tests/test_project_crawler_parsers.py`
- Create: `backend/tests/test_news_crawler_parsers.py`
- Modify: `crawler/projects/crawl_urls.py`
- Modify: `crawler/projects/crawl_details.py`
- Modify: `crawler/news/crawl_articles.py`
- Modify: `data_pipeline/ingestors/projects_ingestor.py`
- Modify: `data_pipeline/ingestors/news_ingestor.py`
- Modify: `backend/tests/test_projects_ingestor.py`
- Modify: `backend/tests/test_news_ingestor.py`
- Modify: `airflow/plugins/pipeline_runner.py`
- Modify: `airflow/dags/weekly_projects_dag.py`
- Modify: `airflow/dags/weekly_news_dag.py`
- Modify: `guide_chay_datapipeline.md`

---

## Task 1: Capture Fixture HTML For Parser Tests

**Files:**
- Create: `backend/tests/fixtures/project_listing_sample.html`
- Create: `backend/tests/fixtures/project_detail_sample.html`
- Create: `backend/tests/fixtures/news_listing_sample.html`
- Create: `backend/tests/fixtures/news_article_sample.html`

- [ ] **Step 1: Save representative project listing HTML**

Create `backend/tests/fixtures/project_listing_sample.html` with at least two project cards. Preserve anchor URLs, title/name nodes, location snippets, and pagination-independent card wrappers. Remove scripts, analytics, inline tracking, and images that are not needed by selectors.

- [ ] **Step 2: Save representative project detail HTML**

Create `backend/tests/fixtures/project_detail_sample.html` with the DOM nodes needed to extract:

```text
slug
name
developer
location
district
city
status
price_range
area_range
project_type
description
amenities
url
```

- [ ] **Step 3: Save representative news listing HTML**

Create `backend/tests/fixtures/news_listing_sample.html` with at least two article links and category/date snippets when available.

- [ ] **Step 4: Save representative news article HTML**

Create `backend/tests/fixtures/news_article_sample.html` with the DOM nodes needed to extract:

```text
title
body
category
source
post_date
url
```

- [ ] **Step 5: Commit fixtures**

```powershell
git add backend/tests/fixtures/project_listing_sample.html backend/tests/fixtures/project_detail_sample.html backend/tests/fixtures/news_listing_sample.html backend/tests/fixtures/news_article_sample.html
git commit -m "add projects and news parser fixtures"
```

Do not include generated live crawl CSVs in this commit.

---

## Task 2: Implement Project URL And Detail Selectors

**Files:**
- Create: `backend/tests/test_project_crawler_parsers.py`
- Modify: `crawler/projects/crawl_urls.py`
- Modify: `crawler/projects/crawl_details.py`

- [ ] **Step 1: Write parser tests for project URLs**

Create `backend/tests/test_project_crawler_parsers.py`:

```python
from pathlib import Path

from crawler.projects import crawl_urls, crawl_details


FIXTURES = Path(__file__).parent / "fixtures"


def test_project_listing_fixture_extracts_urls():
    html = (FIXTURES / "project_listing_sample.html").read_text(encoding="utf-8")
    urls = crawl_urls.extract_project_urls(html, base_url="https://batdongsan.com.vn")

    assert len(urls) >= 2
    assert all(url.startswith("https://batdongsan.com.vn/") for url in urls)
    assert len(urls) == len(set(urls))
```

- [ ] **Step 2: Write parser tests for project details**

Append:

```python
def test_project_detail_fixture_extracts_ingestor_compatible_record():
    html = (FIXTURES / "project_detail_sample.html").read_text(encoding="utf-8")
    record = crawl_details.parse_project_detail(
        html,
        url="https://batdongsan.com.vn/du-an/example-project",
    )

    assert record["slug"] == "example-project"
    assert record["name"]
    assert "developer" in record
    assert "district" in record
    assert "city" in record
    assert "status" in record
    assert "price_range" in record
    assert "area_range" in record
    assert "project_type" in record
    assert "description" in record
    assert "amenities" in record
    assert record["url"].startswith("https://batdongsan.com.vn/")
```

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest backend\tests\test_project_crawler_parsers.py -q
```

Expected: fail because `extract_project_urls()` or `parse_project_detail()` is missing or returns empty scaffold data.

- [ ] **Step 4: Implement `extract_project_urls()`**

In `crawler/projects/crawl_urls.py`, add a pure parser function:

```python
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def extract_project_urls(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href") or ""
        if "/du-an/" not in href and "/du-an-" not in href:
            continue
        absolute = urljoin(base_url, href)
        if absolute not in urls:
            urls.append(absolute)
    return urls
```

Wire the existing Playwright page-fetching code to call this parser instead of returning scaffold-empty output.

- [ ] **Step 5: Implement `parse_project_detail()`**

In `crawler/projects/crawl_details.py`, add a pure parser function that returns exactly the ingestor-compatible keys:

```python
from bs4 import BeautifulSoup
from data_pipeline.clean import slugify


def _text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def parse_project_detail(html: str, *, url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    name = _text(soup, "h1") or _text(soup, "[data-testid='project-title']")
    location = _text(soup, ".project-location, [data-testid='project-location']")
    description = _text(soup, ".project-description, [data-testid='project-description']")
    amenities = [
        " ".join(item.get_text(" ", strip=True).split())
        for item in soup.select(".amenities li, [data-testid='amenity']")
        if item.get_text(strip=True)
    ]
    return {
        "slug": slugify(name) or url.rstrip("/").split("/")[-1],
        "name": name,
        "developer": _text(soup, ".developer, [data-testid='developer']"),
        "location": location,
        "district": _text(soup, ".district, [data-testid='district']"),
        "city": _text(soup, ".city, [data-testid='city']"),
        "total_units": _text(soup, ".total-units, [data-testid='total-units']"),
        "price_range": _text(soup, ".price-range, [data-testid='price-range']"),
        "area_range": _text(soup, ".area-range, [data-testid='area-range']"),
        "status": _text(soup, ".status, [data-testid='status']"),
        "project_type": _text(soup, ".project-type, [data-testid='project-type']"),
        "description": description,
        "amenities": __import__("json").dumps(amenities, ensure_ascii=False),
        "url": url,
    }
```

If the real fixture uses different class names, use selectors that match the fixture and keep this function pure/testable.

- [ ] **Step 6: Run project parser tests**

```powershell
python -m pytest backend\tests\test_project_crawler_parsers.py -q
```

Expected: pass.

- [ ] **Step 7: Commit project parser work**

```powershell
git add crawler/projects/crawl_urls.py crawler/projects/crawl_details.py backend/tests/test_project_crawler_parsers.py
git commit -m "implement project crawler selectors"
```

---

## Task 3: Implement News Article Selectors

**Files:**
- Create: `backend/tests/test_news_crawler_parsers.py`
- Modify: `crawler/news/crawl_articles.py`

- [ ] **Step 1: Write parser tests for news URLs**

Create `backend/tests/test_news_crawler_parsers.py`:

```python
from pathlib import Path

from crawler.news import crawl_articles


FIXTURES = Path(__file__).parent / "fixtures"


def test_news_listing_fixture_extracts_urls():
    html = (FIXTURES / "news_listing_sample.html").read_text(encoding="utf-8")
    urls = crawl_articles.extract_article_urls(html, base_url="https://batdongsan.com.vn")

    assert len(urls) >= 2
    assert all(url.startswith("https://batdongsan.com.vn/") for url in urls)
    assert len(urls) == len(set(urls))
```

- [ ] **Step 2: Write parser tests for article details**

Append:

```python
def test_news_article_fixture_extracts_ingestor_compatible_record():
    html = (FIXTURES / "news_article_sample.html").read_text(encoding="utf-8")
    record = crawl_articles.parse_article(
        html,
        url="https://batdongsan.com.vn/tin-tuc/example-article",
    )

    assert record["title"]
    assert len(record["body"]) > 100
    assert record["category"] in {"news", "legal", "guide", "market"}
    assert record["source"] == "batdongsan.com"
    assert "post_date" in record
    assert record["url"].startswith("https://batdongsan.com.vn/")
```

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest backend\tests\test_news_crawler_parsers.py -q
```

Expected: fail because selectors are scaffold-only or parser functions are missing.

- [ ] **Step 4: Implement `extract_article_urls()`**

In `crawler/news/crawl_articles.py`, add:

```python
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def extract_article_urls(html: str, *, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href") or ""
        if "/tin-tuc/" not in href and "/wiki/" not in href:
            continue
        absolute = urljoin(base_url, href)
        if absolute not in urls:
            urls.append(absolute)
    return urls
```

- [ ] **Step 5: Implement `parse_article()`**

Add:

```python
from bs4 import BeautifulSoup


def _text(soup: BeautifulSoup, selector: str) -> str:
    node = soup.select_one(selector)
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def parse_article(html: str, *, url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = _text(soup, "h1") or _text(soup, "[data-testid='article-title']")
    body_nodes = soup.select("article p, .article-content p, [data-testid='article-body'] p")
    body = "\n".join(
        " ".join(node.get_text(" ", strip=True).split())
        for node in body_nodes
        if node.get_text(strip=True)
    )
    category_text = _text(soup, ".breadcrumb a:last-child, [data-testid='category']")
    category = "news"
    lowered = category_text.lower()
    if "phap ly" in lowered or "pháp lý" in lowered:
        category = "legal"
    elif "thi truong" in lowered or "thị trường" in lowered:
        category = "market"
    elif "huong dan" in lowered or "hướng dẫn" in lowered:
        category = "guide"

    return {
        "title": title,
        "body": body,
        "category": category,
        "source": "batdongsan.com",
        "post_date": _text(soup, "time, .date, [data-testid='post-date']"),
        "url": url,
    }
```

If the fixture exposes dates in non-ISO format, keep parser output as raw text and normalize in `row_to_article()` only if needed in a later task.

- [ ] **Step 6: Run news parser tests**

```powershell
python -m pytest backend\tests\test_news_crawler_parsers.py -q
```

Expected: pass.

- [ ] **Step 7: Commit news parser work**

```powershell
git add crawler/news/crawl_articles.py backend/tests/test_news_crawler_parsers.py
git commit -m "implement news crawler selectors"
```

---

## Task 4: Apply Publish-Before-Index To Projects Ingestion

**Files:**
- Modify: `data_pipeline/ingestors/projects_ingestor.py`
- Modify: `backend/tests/test_projects_ingestor.py`

- [ ] **Step 1: Add result shape test**

In `backend/tests/test_projects_ingestor.py`, add:

```python
from data_pipeline.ingestors import projects_ingestor as pi


def test_project_empty_ingest_result_shape():
    assert pi.empty_ingest_result() == {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }
```

- [ ] **Step 2: Add embedding-failure publish test**

Add:

```python
import pytest


class FailingEmbedder:
    async def embed_texts(self, texts):
        raise RuntimeError("embedding unavailable")


def sample_project_row():
    return {
        "slug": "project-publish-1",
        "name": "Project Publish 1",
        "developer": "Demo Developer",
        "district": "Quan 7",
        "city": "Ho Chi Minh",
        "status": "selling",
        "price_range": "5-7 ty",
        "area_range": "50-80 m2",
        "project_type": "apartment",
        "description": "Project description",
        "amenities": '["pool", "school"]',
        "url": "https://example.test/projects/project-publish-1",
    }


@pytest.mark.asyncio
async def test_project_publish_survives_embedding_failure(monkeypatch):
    async def fake_publish_batch(rows):
        assert rows[0]["slug"] == "project-publish-1"
        return [type("PersistedProject", (), {"id": 201, "slug": "project-publish-1"})()]

    monkeypatch.setattr(pi, "publish_project_batch", fake_publish_batch)
    monkeypatch.setattr(pi, "BGEEmbedder", lambda **kwargs: FailingEmbedder())

    result = await pi.ingest_project_rows([sample_project_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 1
```

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest backend\tests\test_projects_ingestor.py -q
```

Expected: fail because result shape and helper functions do not exist.

- [ ] **Step 4: Add project publish/index helpers**

In `data_pipeline/ingestors/projects_ingestor.py`, mirror the listing plan:

```python
def empty_ingest_result() -> dict[str, int]:
    return {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


async def publish_project_batch(projects_data: list[dict[str, Any]]) -> list[Project]:
    persisted: list[Project] = []
    async with async_session() as session:
        for project_data in projects_data:
            project = await upsert_project(session, project_data)
            persisted.append(project)
        await session.commit()
    return persisted
```

Add `index_project_batch()` that:

- receives `list[tuple[Project, list[dict[str, Any]]]]`
- embeds all chunk texts
- on embed failure returns `{"indexed": 0, "chunks": 0, "index_errors": len(projects_with_chunks)}`
- deletes old `Chunk.parent_type == "project"` rows per project
- inserts new chunks
- returns `indexed`, `chunks`, and `index_errors`

Use the listing plan’s `index_listing_batch()` structure and replace `listing` with `project`, `product_id` with `slug`, and `parent_type` with `"project"`.

- [ ] **Step 5: Refactor `ingest_project_rows()`**

Make `ingest_project_rows()`:

```text
clean row_to_project + build_project_chunks
-> publish_project_batch()
-> result["published"] += len(persisted)
-> index_project_batch()
-> merge index counters
```

Do not let embed failure skip structured `projects` upsert.

- [ ] **Step 6: Run project ingestor tests**

```powershell
python -m pytest backend\tests\test_projects_ingestor.py -q
```

Expected: pass.

- [ ] **Step 7: Commit project publish-before-index**

```powershell
git add data_pipeline/ingestors/projects_ingestor.py backend/tests/test_projects_ingestor.py
git commit -m "publish projects before semantic indexing"
```

---

## Task 5: Apply Publish-Before-Index To News Ingestion

**Files:**
- Modify: `data_pipeline/ingestors/news_ingestor.py`
- Modify: `backend/tests/test_news_ingestor.py`

- [ ] **Step 1: Add result shape test**

In `backend/tests/test_news_ingestor.py`, add:

```python
from data_pipeline.ingestors import news_ingestor as ni


def test_news_empty_ingest_result_shape():
    assert ni.empty_ingest_result() == {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }
```

- [ ] **Step 2: Add embedding-failure publish test**

Add:

```python
import pytest


class FailingEmbedder:
    async def embed_texts(self, texts):
        raise RuntimeError("embedding unavailable")


def sample_article_row():
    return {
        "title": "Article Publish 1",
        "body": "Day la noi dung bai viet bat dong san. " * 10,
        "category": "news",
        "source": "batdongsan.com",
        "post_date": "2026-06-01",
        "url": "https://example.test/news/article-publish-1",
    }


@pytest.mark.asyncio
async def test_news_publish_survives_embedding_failure(monkeypatch):
    async def fake_publish_batch(rows):
        assert rows[0]["url"] == "https://example.test/news/article-publish-1"
        return [type("PersistedArticle", (), {"id": 301, "url": rows[0]["url"]})()]

    monkeypatch.setattr(ni, "publish_article_batch", fake_publish_batch)
    monkeypatch.setattr(ni, "BGEEmbedder", lambda **kwargs: FailingEmbedder())

    result = await ni.ingest_article_rows([sample_article_row()], batch_size=1)

    assert result["published"] == 1
    assert result["indexed"] == 0
    assert result["chunks"] == 0
    assert result["publish_errors"] == 0
    assert result["index_errors"] == 1
```

- [ ] **Step 3: Run tests and confirm failure**

```powershell
python -m pytest backend\tests\test_news_ingestor.py -q
```

Expected: fail because result shape and helper functions do not exist.

- [ ] **Step 4: Add article publish/index helpers**

In `data_pipeline/ingestors/news_ingestor.py`, add:

```python
def empty_ingest_result() -> dict[str, int]:
    return {
        "published": 0,
        "indexed": 0,
        "chunks": 0,
        "publish_errors": 0,
        "index_errors": 0,
    }


async def publish_article_batch(articles_data: list[dict[str, Any]]) -> list[Article]:
    persisted: list[Article] = []
    async with async_session() as session:
        for article_data in articles_data:
            article = await upsert_article(session, article_data)
            persisted.append(article)
        await session.commit()
    return persisted
```

Add `index_article_batch()` that:

- receives `list[tuple[Article, list[dict[str, Any]]]]`
- embeds all chunk texts
- on embed failure returns `{"indexed": 0, "chunks": 0, "index_errors": len(articles_with_chunks)}`
- deletes old `Chunk.parent_type == "article"` rows per article
- inserts new chunks
- returns `indexed`, `chunks`, and `index_errors`

Use the listing plan’s `index_listing_batch()` structure and replace `listing` with `article`, `product_id` with `url`, and `parent_type` with `"article"`.

- [ ] **Step 5: Refactor `ingest_article_rows()`**

Make `ingest_article_rows()`:

```text
clean row_to_article + build_article_chunks
-> publish_article_batch()
-> result["published"] += len(persisted)
-> index_article_batch()
-> merge index counters
```

Do not let embed failure skip structured `articles` upsert.

- [ ] **Step 6: Run news ingestor tests**

```powershell
python -m pytest backend\tests\test_news_ingestor.py -q
```

Expected: pass.

- [ ] **Step 7: Commit news publish-before-index**

```powershell
git add data_pipeline/ingestors/news_ingestor.py backend/tests/test_news_ingestor.py
git commit -m "publish news before semantic indexing"
```

---

## Task 6: Validate CSV Compatibility And Airflow Flow

**Files:**
- Modify: `backend/tests/test_projects_ingestor.py`
- Modify: `backend/tests/test_news_ingestor.py`
- Modify: `airflow/plugins/pipeline_runner.py`
- Modify: `airflow/dags/weekly_projects_dag.py`
- Modify: `airflow/dags/weekly_news_dag.py`

- [ ] **Step 1: Add parser-output compatibility tests**

In project and news ingestor tests, pass rows shaped exactly like parser output from Tasks 2 and 3 into:

```python
await ingest_project_rows([project_parser_record], batch_size=1)
await ingest_article_rows([news_parser_record], batch_size=1)
```

Monkeypatch embedder to return vectors:

```python
class StubEmbedder:
    async def embed_texts(self, texts):
        return [[0.1] * 1024 for _ in texts]
```

Assert:

```python
assert result["published"] == 1
assert result["indexed"] == 1
assert result["chunks"] >= 1
assert result["publish_errors"] == 0
assert result["index_errors"] == 0
```

- [ ] **Step 2: Keep pipeline runner APIs unchanged**

In `airflow/plugins/pipeline_runner.py`, keep:

```python
run_projects_ingestion(csv_path: str, batch_size: int = 25) -> dict[str, int]
run_news_ingestion(csv_path: str) -> dict[str, int]
```

Let them return the new `published/indexed/chunks/publish_errors/index_errors` result dictionaries without translating back to old keys.

- [ ] **Step 3: Clarify DAG descriptions**

In `weekly_projects_dag.py`, set description to:

```python
description="Crawl project CSVs, publish projects for web/API visibility, then index project chunks for chatbot retrieval",
```

In `weekly_news_dag.py`, set description to:

```python
description="Crawl news article CSVs, publish articles for web/API visibility, then index article chunks for chatbot retrieval",
```

Do not change DAG order:

```text
projects: crawl_project_urls -> crawl_project_details -> ingest_projects
news: crawl_news -> ingest_news
```

- [ ] **Step 4: Run targeted compatibility tests**

```powershell
python -m pytest backend\tests\test_projects_ingestor.py backend\tests\test_news_ingestor.py backend\tests\test_pipeline_runner.py backend\tests\test_dag_structure.py -q
```

Expected: pass.

- [ ] **Step 5: Commit compatibility and Airflow updates**

```powershell
git add backend/tests/test_projects_ingestor.py backend/tests/test_news_ingestor.py airflow/plugins/pipeline_runner.py airflow/dags/weekly_projects_dag.py airflow/dags/weekly_news_dag.py
git commit -m "align projects news ingestion with publish before index flow"
```

---

## Task 7: Update Runbooks For Unified Source Flow

**Files:**
- Modify: `guide_chay_datapipeline.md`
- Modify: `docs/pipeline.md`

- [ ] **Step 1: Add unified flow note**

Add this section to `guide_chay_datapipeline.md`:

```markdown
## Unified crawl -> CSV -> publish -> index flow

All crawler stages keep writing CSV artifacts first. Ingestors then publish structured parent rows to PostgreSQL before semantic indexing:

- listings CSV -> `listings` -> `chunks(parent_type='listing')`
- projects CSV -> `projects` -> `chunks(parent_type='project')`
- news CSV -> `articles(category='news')` -> `chunks(parent_type='article')`
- legal documents -> `articles(category='legal')` -> `chunks(parent_type='article')`

The web/API reads parent tables and should not wait for BGE-M3 indexing. Chatbot/RAG reads `chunks` and may lag behind web visibility.
```

- [ ] **Step 2: Add projects/news command examples**

Add:

```markdown
```bash
python -m crawler.projects.crawl_urls --pages 1 20 --output data/raw/projects_urls.csv --workers 3
python -m crawler.projects.crawl_details --input data/raw/projects_urls.csv --output data/raw/projects_details.csv --workers 3
python -m data_pipeline.ingestors.projects_ingestor --csv data/raw/projects_details.csv --batch-size 25

python -m crawler.news.crawl_articles --pages 1 10 --output data/raw/news_articles.csv --workers 2
python -m data_pipeline.ingestors.news_ingestor --csv data/raw/news_articles.csv --batch-size 25
```
```

- [ ] **Step 3: Update `docs/pipeline.md` source matrix**

Add or update the source matrix:

```markdown
| Source | CSV artifact | Parent table for web/API | Chunk parent_type for chatbot |
|---|---|---|---|
| Sale/rent listings | `data/raw/*_details.csv` | `listings` | `listing` |
| Projects | `data/raw/projects_details.csv` | `projects` | `project` |
| News | `data/raw/news_articles.csv` | `articles` | `article` |
| Legal KB | `data/knowledge/raw/*` | `articles` | `article` |
```

- [ ] **Step 4: Run docs grep**

```powershell
rg "Unified crawl|Parent table for web/API|publish structured parent rows" guide_chay_datapipeline.md docs\pipeline.md
```

Expected: both docs describe one unified source flow.

- [ ] **Step 5: Commit docs**

```powershell
git add guide_chay_datapipeline.md docs/pipeline.md
git commit -m "document unified crawl publish index flow"
```

---

## Task 8: End-To-End Verification

**Files:**
- No new source files.

- [ ] **Step 1: Run parser and ingestor tests**

```powershell
python -m pytest backend\tests\test_project_crawler_parsers.py backend\tests\test_news_crawler_parsers.py backend\tests\test_projects_ingestor.py backend\tests\test_news_ingestor.py -q
```

Expected: pass.

- [ ] **Step 2: Run full backend tests**

```powershell
python -m pytest backend\tests -q
```

Expected: pass. Existing expected skips are acceptable.

- [ ] **Step 3: Run syntax check**

```powershell
python -m compileall backend\app data_pipeline chatbot crawler
```

Expected: no syntax errors.

- [ ] **Step 4: Run frontend lint**

```powershell
cd frontend
npm run lint
```

Expected: ESLint exits with code 0.

- [ ] **Step 5: Smoke test project/news crawl commands**

Only after parser tests pass, run small live smoke commands:

```powershell
python -m crawler.projects.crawl_urls --pages 1 1 --output data/raw/project_urls_smoke.csv --workers 1
python -m crawler.projects.crawl_details --input data/raw/project_urls_smoke.csv --output data/raw/project_details_smoke.csv --workers 1 --limit 2
python -m data_pipeline.ingestors.projects_ingestor --csv data/raw/project_details_smoke.csv --batch-size 2

python -m crawler.news.crawl_articles --pages 1 1 --output data/raw/news_articles_smoke.csv --workers 1
python -m data_pipeline.ingestors.news_ingestor --csv data/raw/news_articles_smoke.csv --batch-size 2
```

Expected ingestor output shape:

```text
{'published': <n>, 'indexed': <m>, 'chunks': <k>, 'publish_errors': <x>, 'index_errors': <y>}
```

- [ ] **Step 6: Verify DB parent visibility**

```powershell
docker exec realestate_postgres psql -U admin -d realestate -c "SELECT count(*) FROM projects;"
docker exec realestate_postgres psql -U admin -d realestate -c "SELECT category, count(*) FROM articles GROUP BY category;"
docker exec realestate_postgres psql -U admin -d realestate -c "SELECT parent_type, count(*) FROM chunks GROUP BY parent_type;"
```

Expected: parent table counts reflect published rows; chunks may lag only when index errors are reported.

---

## Public Interfaces And Data Contracts

- Crawler CLIs still write CSV and remain compatible with `guide_chay_datapipeline.md`.
- Projects CSV still feeds `projects_ingestor.py`.
- News CSV still feeds `news_ingestor.py`.
- Ingestor results for projects/news align with listings:
  - `published`
  - `indexed`
  - `chunks`
  - `publish_errors`
  - `index_errors`
- Web/API visibility is based on parent tables:
  - `projects`
  - `articles`
- Chatbot/RAG readiness is based on `chunks`.
- No crawler writes directly to DB in this plan.

---

## Test Cases And Scenarios

- Project listing fixture extracts stable project URLs.
- Project detail fixture produces a CSV row accepted by `row_to_project()`.
- News listing fixture extracts stable article URLs.
- News article fixture produces a CSV row accepted by `row_to_article()`.
- Project publish succeeds even if BGE-M3 indexing fails.
- News publish succeeds even if BGE-M3 indexing fails.
- Re-running the same project/news CSV updates parent rows by `slug`/`url` without duplicates.
- Old chunks are replaced only during semantic index phase.
- Airflow project/news DAGs preserve crawl-before-ingest order.

---

## Assumptions

- This plan depends conceptually on the publish-before-index contract introduced in `2026-06-01-m7-crawl-publish-before-index.md`.
- Listings/sale/rent implementation remains in the listing-focused plan; this plan covers projects/news.
- CSV remains the durable artifact for every crawler.
- Projects/news web pages or APIs may be added later; this plan ensures their parent tables are populated first.
- Existing dirty worktree changes must be preserved; commits should include only files from the task being completed.
