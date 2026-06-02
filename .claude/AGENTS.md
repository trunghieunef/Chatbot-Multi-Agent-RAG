# Real Estate Chatbot v2 — Agent Guide

> Nền tảng bất động sản tích hợp chatbot multi-agent RAG, lấy cảm hứng từ batdongsan.com.vn.

---

## Tổng quan dự án

Ứng dụng full-stack BĐS Việt Nam, đang được xây dựng theo lộ trình milestone (M1 → M5):

1. **Crawler** — Cào dữ liệu từ batdongsan.com.vn (Playwright + Stealth) → CSV
2. **Data Pipeline** — Clean → Chunk (semantic) → Embed (Gemini 768-dim) → PostgreSQL+pgvector
3. **Backend API** — FastAPI, PostgreSQL + pgvector, Redis, JWT auth
4. **Frontend** — Next.js 14+ (App Router), Tailwind CSS v4, React 19
5. **RAG Chatbot** — LangGraph multi-agent + Hybrid retrieval (SQL filter → pgvector kNN → Cohere rerank)

---

## Lộ trình milestone

Plans nằm trong `docs/superpowers/plans/`:

| Milestone | Trạng thái | Nội dung |
|-----------|-----------|----------|
| **M1 — Foundation** | ✅ Hoàn thành (PR #1, branch `m1-foundation`) | Crawler core + sale, clean/chunk/embed pipeline, listings ingestor, hybrid search, property_search agent, Alembic schema (articles + chunks + HNSW) |
| **M2 — Multi-Source** | 🚧 Đang triển khai (branch `m2-multi-source`) | Rent crawler, geocoding (Nominatim/Goong), LLM intent extraction, project + news crawlers/ingestors, hybrid search dispatch theo `parent_type`, market_stats agent |
| **M3 — Airflow** | 📋 Plan ready | LocalExecutor DAGs điều phối crawl → clean → embed → ingest theo lịch |
| **M4 — Legal KB** | 📋 Plan ready | Parser PDF luật (PyMuPDF), chunking theo Khoản, embedding, KB cho legal_advisor |
| **M5 — Polish & Monitoring** | 📋 Plan ready | Redis cache, Prometheus/Grafana, drop legacy `Listing.embedding`, performance tuning |

---

## Kiến trúc pipeline (M1 hiện tại)

```
batdongsan.com.vn
        │
        ▼
crawler/sale/crawl_urls.py  ──►  data/raw/listing_urls.csv
crawler/sale/crawl_details.py ──► data/raw/listing_details.csv
        │
        ▼
data_pipeline/clean.py          (row_to_listing — chuẩn hóa giá/diện tích/location)
        │
        ▼
data_pipeline/chunk.py          (4 chunk types: overview/description/location/intent_tags)
        │
        ▼
data_pipeline/embed.py          (GeminiEmbedder, gemini-embedding-001, output_dim=768)
        │
        ▼
data_pipeline/ingestors/listings_ingestor.py
        │
        ├─► PostgreSQL `listings`  (upsert by product_id)
        └─► PostgreSQL `chunks`    (parent_type='listing', embedding vector(768), HNSW index)
                │
                ▼
chatbot/tools/hybrid_search.py  (4 stages: SQL filter → pgvector kNN → Cohere rerank → resolve)
                │
                ▼
chatbot/agents/property_search.py  (LangGraph async node)
```

### Hybrid Retrieval (M1)

```
User Query
   │
   ├─► extract filters (price_min/max, district, city, bedrooms, listing_type, property_type)
   │
   ├─► Stage 1: SQL filter        → candidate listing_ids (WHERE clauses)
   ├─► Stage 2: pgvector kNN      → top-K by cosine distance (<=>) within candidates
   ├─► Stage 3: Cohere rerank     → reorder by semantic relevance (fallback: vector distance)
   └─► Stage 4: resolve to records → full listing rows for the agent
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | Next.js (App Router) | 16.2.3 |
| UI Framework | React | 19.2.4 |
| Styling | Tailwind CSS | v4 (PostCSS plugin) |
| Icons | Lucide React | 1.8.x |
| Charts | Recharts | 3.8.x |
| Backend | FastAPI | ≥0.115.0 |
| ORM | SQLAlchemy (async) | ≥2.0.36 |
| Migrations | Alembic | latest |
| Database | PostgreSQL + pgvector | PG 16 |
| Cache | Redis | 7 Alpine |
| LLM | Google Gemini 2.0 Flash | via `google-genai` SDK |
| Embeddings | **gemini-embedding-001** (`output_dimensionality=768`) | — |
| Reranker | Cohere `rerank-multilingual-v3.0` | v2 API |
| Agent Framework | LangGraph | ≥0.2.0 |
| Crawler | Playwright + playwright-stealth | ≥1.58.0 |
| Auth | JWT (PyJWT + bcrypt) | — |
| Container | Docker Compose | — |
| Test | pytest + pytest-asyncio | — |

---

## Cấu trúc thư mục (sau M1)

```
RealEstate_Chatbot_v2/
├── backend/                          # FastAPI Backend
│   ├── app/                          # Backend v2 — USE THIS
│   │   ├── main.py                   # FastAPI app + lifespan + CORS
│   │   ├── config.py                 # Pydantic Settings (env vars)
│   │   ├── database.py               # SQLAlchemy async engine + session
│   │   ├── models/                   # ORM models
│   │   │   ├── listing.py            # Listing (legacy `embedding` Vector(768))
│   │   │   ├── project.py            # Project
│   │   │   ├── article.py            # ★ M1: news/legal articles
│   │   │   ├── chunk.py              # ★ M1: parent_type/parent_id/embedding(768) + HNSW
│   │   │   ├── user.py
│   │   │   └── chat.py
│   │   ├── schemas/                  # Pydantic schemas
│   │   ├── routers/                  # listings, market, auth, chat
│   │   └── services/
│   ├── alembic/
│   │   └── versions/
│   │       └── 20260525_0001_m1_foundation.py   # ★ articles + chunks + HNSW
│   ├── tests/                        # ★ pytest test suite
│   │   ├── conftest.py               # sys.path fix (REPO_ROOT + BACKEND_ROOT)
│   │   └── test_*.py
│   ├── requirements.txt
│   └── Dockerfile
│   └── main.py                       # ⚠ Legacy CSV backend — DO NOT USE
│
├── crawler/                          # ★ M1 — replaces old Crawl/
│   ├── core/
│   │   ├── csv_writer.py             # append_csv, read_done_ids, merge_tmp_files
│   │   └── parser.py                 # text_or_empty, attribute_or_empty
│   └── sale/
│       ├── crawl_urls.py             # 8-worker parallel URL listing crawler
│       └── crawl_details.py          # Detail parser, --since flag for incremental
│
├── data_pipeline/                    # ★ M1 — ETL stages
│   ├── clean.py                      # row_to_listing + 7 parser helpers
│   ├── chunk.py                      # build_listing_chunks (4 chunk types)
│   ├── embed.py                      # GeminiEmbedder (retry, batch, 768-dim config)
│   ├── ingestors/
│   │   └── listings_ingestor.py      # CLI: --csv → upsert + chunk + embed
│   └── load_db.py                    # ⚠ Legacy loader
│
├── chatbot/                          # ★ M1 — Multi-agent RAG (replaces RAG/)
│   ├── config.py                     # Mirrors backend/app/config.py
│   ├── state.py                      # ChatState (LangGraph)
│   ├── graph.py                      # StateGraph workflow
│   ├── tools/
│   │   └── hybrid_search.py          # SQL filter → pgvector → Cohere rerank
│   └── agents/
│       ├── router.py
│       ├── property_search.py        # ★ async, calls hybrid_search
│       ├── market_analysis.py        # placeholder (M2 wires to market_stats)
│       ├── legal_advisor.py          # placeholder (M4)
│       └── investment_advisor.py     # placeholder
│
├── frontend/                         # Next.js 14+
│   ├── app/                          # App Router pages
│   ├── components/                   # Header, Footer, ListingCard, ListingGrid, FilterPanel, ChatWidget
│   └── lib/                          # api.ts, types.ts, utils.ts
│
├── docs/
│   └── superpowers/
│       ├── specs/                    # Brainstorming → design docs
│       └── plans/                    # ★ Implementation plans M1-M5
│           ├── 2026-05-25-m1-foundation-pipeline.md       (✅ executed)
│           ├── 2026-05-25-m2-multi-source-pipeline.md    (🚧 active)
│           ├── 2026-05-25-m3-airflow-orchestration.md
│           ├── 2026-05-25-m4-legal-knowledge-base.md
│           └── 2026-05-25-m5-polish-and-monitoring.md
│
├── data/                             # CSV / DB assets (gitignored)
│   └── raw/                          # crawler outputs
│
├── Crawl/                            # ⚠ Legacy crawler scripts (reference only)
├── RAG/                              # ⚠ Legacy RAG scaffold (replaced by chatbot/)
├── FrontEnd_old/                     # ⚠ Legacy HTML/CSS/JS (reference only)
├── batdongsancom-crawler/            # Crawler utils (clean, heatmap)
├── notebooks/                        # 01.EDA.ipynb
├── docker-compose.yml
├── requirements.txt
└── .env
```

---

## Database Schema (M1)

### Bảng chính

| Table | Mô tả | Key columns |
|-------|--------|-------------|
| `listings` | Tin BĐS bán/cho thuê | product_id, title, price, area, bedrooms, listing_type, district, city, latitude, longitude, **embedding vector(768)** (legacy, sẽ drop ở M5) |
| `projects` | Dự án BĐS | slug, name, developer, status, amenities (jsonb), embedding |
| `articles` | ★ M1: Tin tức + văn bản pháp lý | id, title, body, category (`news`/`legal`), source, post_date, url |
| `chunks` | ★ M1: Semantic chunks (canonical embedding store) | id, **parent_type** (`listing`/`project`/`article`), **parent_id**, chunk_type, text, **embedding vector(768)**, HNSW index |
| `users` | Tài khoản | email, hashed_password |
| `chat_sessions`, `chat_messages` | Lịch sử chat | session_id, role, content, agent_used, metadata (jsonb) |

### Vector Search

- Extension: `pgvector`
- **Embedding dimension: 768** (Gemini `gemini-embedding-001` với explicit `output_dimensionality=768`)
- **HNSW index** trên `chunks.embedding` với `m=16, ef_construction=64`, opclass `vector_cosine_ops`
- Similarity: cosine distance `<=>`
- Canonical embedding store là `chunks` (không phải `listings.embedding`); `listings.embedding` giữ lại cho backward-compat tới M5

---

## Cấu hình & Environment

### Required env vars (`.env`)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://admin:...@localhost:5432/realestate
POSTGRES_DB=realestate
POSTGRES_USER=admin
POSTGRES_PASSWORD=<secret>

# Redis
REDIS_URL=redis://localhost:6379/0

# Google Gemini
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.0-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIM=768

# Cohere reranker (M1)
COHERE_API_KEY=<optional, falls back to vector-distance>
RERANK_PROVIDER=cohere
RERANK_MODEL=rerank-multilingual-v3.0

# Geocoding (M2)
GEOCODER_PROVIDER=nominatim
GEOCODER_USER_AGENT=realestate-chatbot/0.1 (contact@example.com)
GEOCODER_RATE_LIMIT_SECONDS=1.0
GOONG_API_KEY=

# Intent extraction (M2)
INTENT_EXTRACTOR=rule              # 'rule' | 'gemini'
GEMINI_INTENT_MODEL=gemini-2.0-flash

# JWT
JWT_SECRET_KEY=<secret>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440

# CORS
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

### Docker Services

| Service | Image | Port |
|---------|-------|------|
| PostgreSQL + pgvector | `pgvector/pgvector:pg16` | 5432 |
| Redis | `redis:7-alpine` | 6379 |
| Backend | Custom (FastAPI) | 8000 |
| Frontend | Custom (Next.js) | 3000 |

> ChromaDB đã loại khỏi pipeline chính (M1 quyết định dùng pgvector làm vector store duy nhất). Container `chromadb` trong `docker-compose.yml` còn lại chỉ để legacy.

---

## Quy ước code

### Backend (Python)

- **Framework**: FastAPI async/await
- **ORM**: SQLAlchemy 2.0 async (`asyncpg` driver)
- **Validation**: Pydantic v2 schemas trong `backend/app/schemas/`
- **Config**: Pydantic Settings từ `.env`
- **API versioning**: prefix `/api/v1/`
- **Type hints**: bắt buộc cho mọi function signature
- **Naming**: snake_case Python, PascalCase classes
- **Migrations**: Alembic — không sửa migration cũ, luôn tạo file mới với revision id `YYYYMMDD_NNNN_description.py`

### Data Pipeline (Python)

- **Stages**: clean → chunk → embed → ingest, mỗi stage là module độc lập
- **TDD**: viết test trước, run để confirm fail, implement, run để pass, commit
- **Tests**: `backend/tests/test_*.py` với pytest + pytest-asyncio
- **Imports**: `data_pipeline.*` import được từ repo root nhờ `backend/tests/conftest.py` chèn cả `REPO_ROOT` và `BACKEND_ROOT` vào `sys.path`

### Frontend (TypeScript/React)

- **Framework**: Next.js 14+ App Router (`app/`)
- **Styling**: Tailwind CSS v4 (PostCSS plugin `@tailwindcss/postcss`, KHÔNG có `tailwind.config.ts`)
- **Language**: TypeScript strict
- **Components**: functional + hooks, PascalCase
- **API calls**: qua `lib/api.ts`
- **Types**: `lib/types.ts`

### Chatbot / RAG (Python)

- **Framework**: LangGraph (StateGraph) — hỗ trợ async nodes qua `ainvoke`
- **LLM**: Google Gemini via `google-genai` SDK
- **State**: `ChatState` (extends `MessagesState`)
- **Pattern**: Router → Specialized Agents → Synthesizer
- **Hybrid retrieval**: dùng `chatbot/tools/hybrid_search.py` thay vì raw SQL
- **Fallback**: keyword routing khi không có `GEMINI_API_KEY`; vector-distance rerank khi không có `COHERE_API_KEY`

### Crawler (Python)

- **Tool**: Playwright + playwright-stealth
- **Parallel**: 8 workers cho URL listing crawl
- **Output**: CSV → `data/raw/`
- **Helpers**: dùng `crawler.core.csv_writer` (`append_csv`, `read_done_ids`) và `crawler.core.parser`
- **Anti-detection**: stealth, random delays, UA rotation
- **Incremental**: `--since` flag trong `crawl_details.py` để skip product_id đã có

---

## Multi-Agent RAG Architecture

### Agents (M1)

| Agent | Trigger | Trạng thái |
|-------|---------|-----------|
| **Router** | (all queries) | Classify intent + extract filters |
| **Property Search** | tìm/mua/thuê/căn hộ/nhà/đất | ★ M1: hybrid_search(parent_type='listing') |
| **Market Analysis** | giá/thị trường/xu hướng/thống kê | M2: SQL aggregates qua `market_stats.py` |
| **Legal Advisor** | pháp lý/luật/thủ tục/công chứng/thuế | M4: hybrid_search(parent_type='article', category='legal') |
| **Investment Advisor** | đầu tư/ROI/lợi nhuận | M5+: ROI calculator |

### LangGraph Workflow

```
START → router → [conditional routing] → agent(s) → synthesizer → END
```

### State Schema (`ChatState`)

```python
class ChatState(MessagesState):
    user_query: str
    intent: str
    target_agents: list[str]
    search_filters: dict          # price_min/max, district, city, bedrooms, listing_type, ...
    retrieved_listings: list
    retrieved_docs: list
    agent_results: dict           # {agent_name: {content, sources, confidence}}
    final_response: str
    sources: list[dict]
    suggested_actions: list[str]
    agent_used: str
```

---

## API Endpoints

### Listings
```
GET  /api/v1/listings              # list + filter + pagination
GET  /api/v1/listings/{id}
GET  /api/v1/listings/search       # full-text
GET  /api/v1/listings/similar/{id} # vector similarity
```

### Market
```
GET  /api/v1/market/stats
GET  /api/v1/market/price-trends
GET  /api/v1/market/heatmap
```

### Chat
```
POST /api/v1/chat                  # REST
WS   /api/v1/chat/ws               # WebSocket
GET  /api/v1/chat/sessions
GET  /api/v1/chat/sessions/{id}
```

### Auth
```
POST /api/v1/auth/register
POST /api/v1/auth/login
```

### System
```
GET  /api/v1/health
```

---

## Trạng thái hiện tại

### ✅ Đã hoàn thành (M1)
- `crawler/core/` shared helpers + `crawler/sale/` URL + detail crawlers (refactor từ `Crawl/`)
- `data_pipeline/clean.py` — 8 parser/normalizer functions, rent vs sale price unit
- `data_pipeline/chunk.py` — 4 semantic chunk types (overview/description/location/intent_tags) với rule-based intent tagging
- `data_pipeline/embed.py` — `GeminiEmbedder` với retry, batch, explicit `output_dimensionality=768`
- `data_pipeline/ingestors/listings_ingestor.py` — CLI upsert + chunk + embed
- Alembic migration `20260525_0001` — tạo `articles` + `chunks` (parent polymorphic) + HNSW
- `chatbot/tools/hybrid_search.py` — 4-stage retrieval, Cohere fallback
- `chatbot/agents/property_search.py` — async LangGraph node gọi hybrid_search
- Test suite `backend/tests/` (pytest + pytest-asyncio)
- PR #1: `m1-foundation` → `demo`

### 🚧 Đang triển khai (M2 — branch `m2-multi-source`)
13 tasks theo `docs/superpowers/plans/2026-05-25-m2-multi-source-pipeline.md`:
- Geocoding config (Nominatim/Goong) + intent extraction config
- Shared `crawler/core/listing_detail_parser.py` cho sale + rent
- `crawler/rent/` package
- `data_pipeline/enrich.py` — `NominatimGeocoder` + `GeminiIntentExtractor`
- Listings ingestor: thêm enrichment pass (lat/lon + intent_tags)
- `crawler/projects/` + `data_pipeline/ingestors/projects_ingestor.py`
- `crawler/news/` + `data_pipeline/ingestors/news_ingestor.py`
- Hybrid search dispatch theo `parent_type` (listing/project/article)
- `chatbot/tools/market_stats.py` + wire market_analysis agent
- Property search forwards `listing_type` filter
- Migration `20260601_0002` — geocode + project + article indexes

### 📋 Backlog
- M3: Airflow LocalExecutor DAGs
- M4: Legal PDF parser (PyMuPDF) + KB
- M5: Redis cache, Prometheus/Grafana, drop legacy `Listing.embedding`

---

## Hướng dẫn phát triển

### Khởi chạy services
```bash
docker-compose up -d postgres redis
```

### Chạy migrations
```bash
cd backend
alembic upgrade head
```

### Backend dev server
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

### Pipeline (M1)
```bash
# Crawl
python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/listing_urls.csv
python -m crawler.sale.crawl_details --input data/raw/listing_urls.csv --output data/raw/listing_details.csv

# Ingest (clean + chunk + embed + upsert)
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/listing_details.csv --batch-size 50
```

### Tests
```bash
cd backend
python -m pytest tests -q
```

### Verification
```bash
python -m compileall backend/app chatbot data_pipeline crawler
```

---

## Lưu ý quan trọng

1. **Hai backend**: `backend/main.py` (legacy CSV) vs `backend/app/main.py` (v2). **Luôn dùng `backend/app/main.py`**.

2. **Legacy folders**: `RAG/`, `Crawl/`, `FrontEnd_old/`, `backend/main.py`, `data_pipeline/load_db.py` — giữ để tham khảo, KHÔNG dùng cho dev mới. Code mới đi vào `chatbot/`, `crawler/`, `data_pipeline/{clean,chunk,embed,ingestors}.py`, `backend/app/`.

3. **Embedding model**: Bắt buộc `gemini-embedding-001` với `output_dimensionality=768` (cấu hình qua `types.EmbedContentConfig`). Default model trả 3072 dims, không khớp `Vector(768)` schema. Tên model `text-embedding-004` hoặc `gemini-embedding-2` đều SAI / không tồn tại trên API hiện tại.

4. **Tailwind v4**: PostCSS plugin `@tailwindcss/postcss`, không có `tailwind.config.ts`.

5. **pgvector + HNSW**: extension `vector` được enable trong `database.py` → `init_db()`. HNSW index trên `chunks.embedding` đã có sẵn từ migration M1.

6. **Canonical embedding store**: là bảng `chunks` (parent_type/parent_id/embedding). Cột `listings.embedding` cũ chỉ giữ tới M5 thì drop. Code mới luôn query qua `chunks` + `chatbot.tools.hybrid_search`.

7. **Cohere optional**: `COHERE_API_KEY` không bắt buộc; thiếu thì rerank fallback về vector cosine distance.

8. **Subagent-driven development**: Plans M1-M5 được thiết kế để chạy bằng `superpowers:subagent-driven-development` — implementer → spec reviewer → code quality reviewer per task, mỗi task tự commit. M1 đã exec theo workflow này thành công.

9. **Branching**: Mỗi milestone 1 branch (`m1-foundation`, `m2-multi-source`, ...). PR vào `demo` (hoặc `main`). Không commit trực tiếp lên `main`/`demo`.

10. **Ngôn ngữ**: UI, prompts LLM, response chatbot bằng tiếng Việt. Code comments / docstrings / commit messages bằng tiếng Anh ngắn gọn.

11. **Data files**: CSV trong `data/raw/` không track git. Cần chạy crawler để lấy dữ liệu.

12. **GEMINI_API_KEY**: cần set để embedder + router LLM hoạt động. Thiếu → router fallback keyword routing, embedder fail.
