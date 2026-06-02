# Pipeline Crawl + Index batdongsan.com cho Multi-Agent Chatbot

## Context

Dự án `RealEstate_Chatbot_v2` đã có các mảnh ghép rời rạc:

- `Crawl/01.crawl_listing_url.py`, `Crawl/02.crawl_listing_details.py` — Playwright crawler chỉ cho **nhà đất bán**
- `data/` — ~6k listings dạng CSV
- `data_pipeline/load_db.py` — load CSV → PostgreSQL + pgvector (đã có parser giá/diện tích, nhưng chưa có embedding)
- `backend/app/` — FastAPI v2 với SQLAlchemy models (listings)
- `chatbot/` — multi-agent scaffold plus backend-integrated RAG services; retrieval now uses PostgreSQL + pgvector chunks with BGE-M3 embeddings.
- `frontend/` — Next.js

**Cái thiếu:** không có pipeline gắn kết end-to-end. Chatbot không thể truy vấn được dữ liệu vì:
1. Crawler chỉ phủ nhà bán, thiếu cho thuê/dự án/tin tức/pháp lý
2. Không có cleaning → enrichment → embedding → vector index pipeline
3. Không có scheduler để cập nhật incremental
4. Không có hybrid retriever (SQL filter + vector + rerank) cho agents dùng

**Mục tiêu:** xây pipeline đầy đủ từ crawl → clean → enrich → load DB → chunk → embed → vector index, orchestrate bằng Airflow, để Multi-Agent Chatbot có data nền tảng trả lời mọi câu hỏi BĐS.

## Quyết định kiến trúc đã chốt

| Hạng mục | Quyết định |
|---|---|
| Phạm vi crawl | Nhà bán + nhà cho thuê + dự án + tin tức/pháp lý |
| Cadence | Incremental theo lịch (Airflow daily/weekly/monthly) |
| Storage | PostgreSQL 16 + pgvector (single source of truth) |
| Orchestrator | Apache Airflow |
| Embedding model | BGE-M3 `BAAI/bge-m3` dense vectors (1024 dim) |
| Indexing strategy | Hybrid: SQL filter + chunked vectors + rerank |
| Chunking | Mỗi listing → nhiều chunk semantic (overview / description / location / intent_tags) |
| Reranker | Cohere/Jina Rerank API (multilingual) |

**Current HEAD note:** The active retrieval path is PostgreSQL + pgvector, not ChromaDB/Qdrant. Current HEAD uses BGE-M3 dense embeddings with 1024 dimensions. Migration `20260801_0007_bge_m3_embeddings.py` clears existing `chunks`, changes `chunks.embedding` to `vector(1024)`, and requires re-ingesting indexed sources.

**Crawler status note:** `crawler/projects/` and `crawler/news/` now have fixture-backed parser selectors. Live smoke runs should still start small because batdongsan.com.vn DOM and anti-bot behavior can change.

**Publish-first listing ingestion note:** Current listing ingestion is intentionally publish-first: crawled detail CSV rows are upserted into `listings` before semantic chunks are embedded. The web UI only depends on `listings`; chatbot/RAG depends on `chunks`, so embedding failures must not prevent crawled listings from appearing on the site.

**Unified source flow note:** Current source ingestion is intentionally publish-first: crawled CSV rows are published as structured parent rows before semantic chunks are embedded. The web/API reads parent tables; chatbot/RAG reads `chunks`, so embedding failures must not prevent crawled parent records from appearing in API-visible tables.

| Source | CSV artifact | Parent table for web/API | Chunk parent_type for chatbot |
|---|---|---|---|
| Sale/rent listings | `data/raw/*_details.csv` | `listings` | `listing` |
| Projects | `data/raw/projects_details.csv` | `projects` | `project` |
| News | `data/raw/news_articles.csv` | `articles` | `article` |
| Legal KB | `data/knowledge/raw/*` | `articles` | `article` |

## Kiến trúc tổng thể

```
┌─────────────────────────── AIRFLOW DAGs ───────────────────────────┐
│  daily_listings_dag (sale + rent)                                  │
│  weekly_projects_dag (du-an)                                       │
│  weekly_news_dag (tin-tuc)                                         │
│  monthly_legal_kb_dag (Luật Đất đai/Nhà ở/KD BĐS)                  │
└────────────────────────────────┬───────────────────────────────────┘
                                 │
       crawl → clean → enrich → load DB → chunk → embed
                                 │
                                 ▼
   ┌────────────────────────────────────────────────────────┐
   │           PostgreSQL 16 + pgvector                     │
   │  listings | projects | articles  (structured)          │
   │  chunks  (parent_id, chunk_type, embedding vector(1024))│
   └────────────────────────────────────────────────────────┘
                                 ▲
                                 │ Hybrid retriever
                                 │ (SQL filter → vector kNN → rerank)
                                 │
                ┌────────────────┴──────────────────┐
                │   chatbot/ (LangGraph multi-agent) │
                │   Router → Property/Market/Legal/Inv│
                └────────────────────────────────────┘
```

## Chi tiết các thành phần

### 1. Crawler layer — refactor `Crawl/` thành `crawler/`

**Lý do refactor:** code hiện tại trong `Crawl/01.crawl_listing_url.py` và `Crawl/02.crawl_listing_details.py` lặp logic Playwright/stealth/CSV writer. Tách thành module dùng chung để 4 loại crawler tái sử dụng.

```
crawler/
├── __init__.py
├── core/
│   ├── browser.py        # Playwright context + stealth (rút từ 01.crawl_listing_url.py:104-130)
│   ├── csv_writer.py     # _append_csv, dedupe (rút từ 01.crawl_listing_url.py:181-215)
│   └── parser.py         # _text helper, retry logic
├── sale/
│   ├── crawl_urls.py     # tái dùng logic 01.crawl_listing_url.py, BASE_URL=/nha-dat-ban
│   └── crawl_details.py  # tái dùng logic 02.crawl_listing_details.py
├── rent/
│   ├── crawl_urls.py     # BASE_URL = /nha-dat-cho-thue
│   └── crawl_details.py  # parser tương tự sale, thêm field price_unit='month'
├── projects/
│   └── crawl_projects.py # /du-an: name, developer, location, price_range, status, units, amenities, description
└── news/
    └── crawl_articles.py # /tin-tuc: title, body, category, post_date, author, url
```

**Mỗi crawler nhận flag `--since YYYY-MM-DD`** để incremental: chỉ cào URL có `post_date` sau ngày đó. Tái dùng `_read_done_ids()` ở `Crawl/02.crawl_listing_details.py:359` để skip đã crawled.

**File quan trọng:**
- `Crawl/01.crawl_listing_url.py` → di chuyển logic vào `crawler/sale/crawl_urls.py` + `crawler/core/`
- `Crawl/02.crawl_listing_details.py` → `crawler/sale/crawl_details.py` + `crawler/core/`
- `Crawl/merge.py` → `crawler/core/csv_writer.py` (gộp `_merge_tmp_files`)

### 2. Cleaning + enrichment layer — mở rộng `data_pipeline/`

```
data_pipeline/
├── clean.py        # parse_price_billion, parse_area, parse_int_safe (đã có ở load_db.py:31-74)
│                   # — tách ra để dùng cho cả 3 ingestors
├── enrich.py       # geocode address → lat/lon (Goong API hoặc Nominatim)
│                   # — extract intent_tags từ description: "gần trường", "view sông", "an ninh"
│                   # — classify property_type chi tiết hơn (đã có rule ở load_db.py:87)
├── chunk.py        # build_chunks(record) → list[Chunk]:
│                   #   - overview: title + property_type + location_summary + price + area
│                   #   - description: mô tả gốc, split nếu >800 từ
│                   #   - location: address + landmarks gần (school, hospital, market)
│                   #   - intent_tags: tags tự động extract bằng LLM hoặc rule
├── embed.py        # batch BGE-M3 embeddings (1024 dim)
│                   # — batch size 100, retry exponential backoff
├── load_db.py      # đã có (load_db.py:165), mở rộng:
│                   #   - upsert thay vì insert-only (handle update listing)
│                   #   - sau insert listing → gọi chunk.py + embed.py → insert chunks
└── ingestors/
    ├── listings_ingestor.py  # orchestrate clean → enrich → load → chunk → embed
    ├── projects_ingestor.py
    └── news_ingestor.py
```

**Tái dùng:**
- `parse_price_billion()`, `parse_area()`, `parse_int_safe()`, `parse_price_per_m2()`, `determine_listing_type()`, `determine_property_type()`, `extract_location()`, `row_to_listing()` — đã có ở [data_pipeline/load_db.py](data_pipeline/load_db.py) — **chuyển sang `data_pipeline/clean.py`** để 3 ingestors đều dùng được.
- `async_session`, `engine`, `Base` — từ `backend/app/database.py`.

### 3. Schema PostgreSQL — mở rộng `backend/app/models/`

Đã có `Listing` model (theo [data_pipeline/load_db.py:25](data_pipeline/load_db.py#L25)). Cần thêm:

```python
# backend/app/models/project.py
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    developer: Mapped[str | None]
    location: Mapped[str | None]
    district: Mapped[str | None]
    city: Mapped[str | None]
    latitude: Mapped[float | None]
    longitude: Mapped[float | None]
    total_units: Mapped[int | None]
    price_range: Mapped[str | None]
    status: Mapped[str | None]   # 'upcoming' | 'selling' | 'completed'
    amenities: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    description: Mapped[str | None]
    url: Mapped[str | None]
    created_at: Mapped[datetime]

# backend/app/models/article.py
class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str]
    category: Mapped[str | None]   # 'news' | 'legal' | 'guide'
    source: Mapped[str | None]     # 'batdongsan.com' | 'luat-dat-dai-2024.pdf'
    post_date: Mapped[date | None]
    url: Mapped[str | None]
    created_at: Mapped[datetime]

# backend/app/models/chunk.py
class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_type: Mapped[str]    # 'listing' | 'project' | 'article'
    parent_id: Mapped[int]      # FK theo parent_type (composite logic ở app layer)
    chunk_type: Mapped[str]     # 'overview' | 'description' | 'location' | 'intent_tags'
    text: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
    created_at: Mapped[datetime]

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

**Migration:** dùng Alembic (chưa có trong repo). Tạo `backend/alembic/` và viết revision đầu tiên export full schema hiện tại + thêm `projects`, `articles`, `chunks`.

### 4. Hybrid retriever — `chatbot/tools/hybrid_search.py`

Đây là tool quan trọng nhất, được Property Search Agent + Market Agent gọi.

```python
# chatbot/tools/hybrid_search.py
async def hybrid_search(
    query: str,
    filters: dict,          # {price_min, price_max, district, bedrooms, listing_type, ...}
    parent_type: str = "listing",
    top_k: int = 20,
    rerank_to: int = 5,
) -> list[dict]:
    # Stage 1: SQL filter — chọn candidate listings/projects theo structured filters
    candidate_ids = await sql_filter(parent_type, filters)
    if not candidate_ids:
        return []

    # Stage 2: Vector kNN — embed query, search trong chunks thuộc candidates
    query_emb = await gemini_embed(query)
    chunks = await pgvector_knn(
        query_emb,
        parent_type=parent_type,
        parent_ids=candidate_ids,
        k=top_k,
    )

    # Stage 3: Rerank — cross-encoder relevance scoring
    reranked = await cohere_rerank(query, chunks, top_n=rerank_to)

    # Stage 4: Resolve — gom chunks về parent record, dedupe, attach metadata
    return await resolve_to_records(reranked, parent_type)
```

**Tích hợp với agents:**
- `chatbot/agents/property_search.py` — gọi `hybrid_search(parent_type='listing')`
- `chatbot/agents/market_analysis.py` — chủ yếu SQL aggregate, ít vector
- `chatbot/agents/legal_advisor.py` — gọi `hybrid_search(parent_type='article', filters={category: 'legal'})`
- `chatbot/agents/investment_advisor.py` — kết hợp listing + market data

### 5. Airflow DAGs — `airflow/`

```
airflow/
├── docker-compose.airflow.yml    # webserver + scheduler + postgres-airflow
│                                 # — postgres-airflow tách khỏi postgres-app để metadata isolation
├── Dockerfile                    # Python 3.11 + Playwright + project deps
├── dags/
│   ├── daily_listings_dag.py     # sale + rent, schedule '@daily 02:00 ICT', incremental --since
│   ├── weekly_projects_dag.py    # schedule 'weekly Sunday 03:00'
│   ├── weekly_news_dag.py        # schedule 'weekly Sunday 04:00'
│   └── monthly_legal_kb_dag.py   # schedule '@monthly', re-ingest văn bản luật khi có update
├── plugins/
│   └── operators/
│       └── crawler_operator.py   # PythonOperator wrapper gọi crawler/* + data_pipeline/*
└── requirements.txt
```

**Pattern mỗi DAG:**

```
crawl_urls → crawl_details → clean → enrich → load_db → chunk_and_embed → mark_active
```

- Mỗi task retry 3 lần với exponential backoff
- XCom truyền số rows giữa task để báo cáo
- Email/Slack alert khi DAG fail
- `mark_active` = update `is_active=False` cho listings có `expiry_date < today`

### 6. Knowledge base pháp lý

Pipeline riêng vì input là PDF/HTML văn bản luật, không phải web page batdongsan.

```
data/knowledge/
├── raw/           # PDF: Luật Đất đai 2024, Luật Nhà ở 2023, Luật KD BĐS 2023, Nghị định, Thông tư
├── parsed/        # markdown sau khi parse PDF (PyMuPDF)
└── ingested/      # log files đã ingest
```

**`monthly_legal_kb_dag.py`:**
1. Quét `data/knowledge/raw/` tìm file mới hoặc đã đổi (so sánh checksum)
2. Parse PDF → markdown bằng PyMuPDF
3. Chunk theo cấu trúc luật: Chương → Điều → Khoản → Điểm
4. Embed mỗi chunk
5. Insert vào `articles` (parent record) + `chunks` (parent_type='article', category='legal')

## Cấu trúc thư mục cuối

```
RealEstate_Chatbot_v2/
├── crawler/                  # [MỚI] refactor từ Crawl/
│   ├── core/
│   ├── sale/
│   ├── rent/
│   ├── projects/
│   └── news/
├── data_pipeline/            # [MỞ RỘNG]
│   ├── clean.py              # tách từ load_db.py
│   ├── enrich.py             # [MỚI] geocode, intent tags
│   ├── chunk.py              # [MỚI] semantic chunking
│   ├── embed.py              # [MỚI] BGE-M3 batch embed
│   ├── load_db.py            # [SỬA] upsert + chunk+embed integration
│   └── ingestors/            # [MỚI]
│       ├── listings_ingestor.py
│       ├── projects_ingestor.py
│       └── news_ingestor.py
├── backend/
│   ├── app/
│   │   ├── models/           # [MỞ RỘNG]
│   │   │   ├── listing.py    # đã có
│   │   │   ├── project.py    # [MỚI]
│   │   │   ├── article.py    # [MỚI]
│   │   │   └── chunk.py      # [MỚI]
│   │   └── ...
│   └── alembic/              # [MỚI] migrations
├── chatbot/
│   └── tools/
│       └── hybrid_search.py  # [MỚI] SQL filter → vector kNN → rerank
├── airflow/                  # [MỚI]
│   ├── docker-compose.airflow.yml
│   ├── Dockerfile
│   ├── dags/
│   └── plugins/
├── data/
│   ├── raw/                  # CSV từ crawler
│   ├── processed/
│   └── knowledge/            # [MỚI] PDF luật
├── docker-compose.yml        # [SỬA] thêm pgvector image, link Airflow
└── Crawl/                    # [GIỮ TẠM] để rollback, xoá sau khi crawler/ stable
```

## Critical files to modify or create

| File | Action |
|---|---|
| [Crawl/01.crawl_listing_url.py](Crawl/01.crawl_listing_url.py) | Refactor → `crawler/sale/crawl_urls.py` + `crawler/core/browser.py` |
| [Crawl/02.crawl_listing_details.py](Crawl/02.crawl_listing_details.py) | Refactor → `crawler/sale/crawl_details.py` + `crawler/core/parser.py` |
| [data_pipeline/load_db.py](data_pipeline/load_db.py) | Tách parsers → `clean.py`; thêm chunk+embed step |
| [chatbot/config.py](chatbot/config.py) | Thêm `COHERE_API_KEY`, `EMBEDDING_DIM=1024`, `CHUNK_SIZE_TOKENS=400` |
| [chatbot/state.py](chatbot/state.py) | Đã có — không sửa |
| [chatbot/graph.py](chatbot/graph.py) | Đã có — agents sẽ dùng `hybrid_search` mới |
| [docker-compose.yml](docker-compose.yml) | Đảm bảo `postgres` dùng `pgvector/pgvector:pg16` image |
| `crawler/rent/crawl_urls.py` | [MỚI] BASE_URL=/nha-dat-cho-thue |
| `crawler/projects/crawl_projects.py` | [MỚI] schema dự án |
| `crawler/news/crawl_articles.py` | [MỚI] schema bài viết |
| `data_pipeline/enrich.py` | [MỚI] geocode + intent_tags |
| `data_pipeline/chunk.py` | [MỚI] semantic chunking 4 loại |
| `data_pipeline/embed.py` | [MỚI] BGE-M3 batch embed |
| `chatbot/tools/hybrid_search.py` | [MỚI] hybrid retriever |
| `backend/app/models/project.py`, `article.py`, `chunk.py` | [MỚI] |
| `backend/alembic/` | [MỚI] init + migration đầu tiên |
| `airflow/dags/*.py` | [MỚI] 4 DAGs |
| `airflow/docker-compose.airflow.yml` | [MỚI] |

## Verification plan

End-to-end test trên 1 nhánh nhỏ (sale only) trước khi mở rộng:

1. **Schema migration**
   - `cd backend && alembic upgrade head`
   - Kiểm tra: `\dt` thấy `listings`, `projects`, `articles`, `chunks`; `\d chunks` thấy index HNSW

2. **Crawler refactored**
   - `python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/sale_urls_test.csv`
   - Output: ~100-150 URLs, không lỗi

3. **Ingestion pipeline tay**
   - `python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_urls_test_details.csv`
   - Kiểm tra DB: `SELECT count(*) FROM listings; SELECT count(*) FROM chunks WHERE parent_type='listing';`
   - Mỗi listing → 3-4 chunks; embedding không null; HNSW index dùng được (`EXPLAIN ANALYZE` cho 1 vector query)

4. **Hybrid retriever**
   - Script test: `python -m chatbot.tools.hybrid_search --query "căn hộ 2PN Quận 7 dưới 5 tỷ"`
   - Kết quả: top 5 listings, có rerank score, có sources kèm chunk text

5. **End-to-end chatbot**
   - `cd backend && uvicorn app.main:app --reload`
   - POST `/api/v1/chat` với query trên
   - Response chứa listings phù hợp, agent_used='property_search'

6. **Airflow DAG**
   - `cd airflow && docker compose -f docker-compose.airflow.yml up -d`
   - UI `http://localhost:8080`, trigger `daily_listings_dag` thủ công
   - Tất cả task xanh, listings mới xuất hiện trong DB

7. **Incremental**
   - Chạy DAG 2 lần liên tiếp → lần 2 chỉ insert listings mới (so sánh `created_at`)

## Phasing đề xuất

Vì scope rất lớn (4 loại data + Airflow + hybrid search), nên chia thành các milestones triển khai tuần tự — mỗi milestone là một implementation plan riêng:

- **M1: Foundation** — refactor `crawler/`, schema mới (project/article/chunk), Alembic, `data_pipeline/clean+chunk+embed.py`, `hybrid_search.py`. Chỉ cho **sale**. Test end-to-end thủ công.
- **M2: Mở rộng nguồn** — thêm rent + projects + news crawlers + ingestors.
- **M3: Airflow** — đóng gói pipeline thành DAGs, deploy Airflow trong docker-compose.
- **M4: Knowledge base pháp lý** — PDF parser + monthly DAG.
- **M5: Polish** — alerting, monitoring, performance tuning HNSW params, rerank caching.

Plan này tập trung vào kiến trúc tổng thể. Sau khi approve, milestone đầu tiên (M1) sẽ được viết chi tiết bằng `superpowers:writing-plans` skill.
