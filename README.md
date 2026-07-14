# RealEstate Chatbot v2

Nền tảng tìm kiếm, phân tích và tư vấn bất động sản Việt Nam — end-to-end từ crawl dữ liệu, ETL pipeline, đến web frontend và chatbot multi-agent RAG.

> Đồ án tốt nghiệp — Trần Trung Hiếu

---

## Mục lục

- [Kiến trúc tổng quan](#kiến-trúc-tổng-quan)
- [Công nghệ sử dụng](#công-nghệ-sử-dụng)
- [Yêu cầu hệ thống](#yêu-cầu-hệ-thống)
- [Cài đặt nhanh bằng Docker](#cài-đặt-nhanh-bằng-docker)
- [Cài đặt thủ công (phát triển local)](#cài-đặt-thủ-công-phát-triển-local)
- [Biến môi trường](#biến-môi-trường)
- [Cấu trúc dự án](#cấu-trúc-dự-án)
- [Chatbot multi-agent RAG](#chatbot-multi-agent-rag)
- [Data pipeline & Crawler](#data-pipeline--crawler)
- [Monitoring](#monitoring)
- [API Backend](#api-backend)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Kiến trúc tổng quan

Hệ thống gồm **4 service Python + 1 frontend Next.js**, giao tiếp qua HTTP nội bộ:

```
Browser ──► Frontend (Next.js :3000)
               │
               ▼
         Backend (FastAPI :8000)          ← public API, auth, listings, chat
               │  POST /internal/agent/chat
               │  header: X-Internal-Agent-Key
               ▼
         Agent Service (LangGraph :8100)  ← multi-agent RAG (internal only)

         Pipeline Worker (FastAPI :8200)  ← crawl / embed / ingest (internal only)

         PostgreSQL 16 + pgvector   Redis 7
```

```mermaid
flowchart TD
    User["Người dùng"] --> FE["Next.js 16\n:3000"]
    FE --> BE["FastAPI Backend\n:8000"]
    BE --> PG["PostgreSQL 16 + pgvector"]
    BE --> RD["Redis 7"]
    BE --> AS["Agent Service\nLangGraph :8100"]
    BE --> PW["Pipeline Worker\n:8200"]
    AS --> Gemini["Google Gemini 2.5 Flash"]
    PW --> Crawler["Playwright Crawlers"]
    PW --> Ingestor["Data Pipeline"]
    Ingestor --> PG
    Prometheus --> BE & PG & RD
    Grafana --> Prometheus
```

---

## Công nghệ sử dụng

| Lớp | Công nghệ |
|---|---|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS v4, Recharts |
| **Backend** | FastAPI, SQLAlchemy 2.0 async (asyncpg), Alembic, Pydantic v2 |
| **AI / RAG** | LangGraph, Google Gemini 2.5 Flash, BAAI/bge-m3 (1024-dim), pgvector HNSW |
| **Reranker** | Cohere `rerank-multilingual-v3.0` (tùy chọn) |
| **Database** | PostgreSQL 16 + pgvector, Redis 7 |
| **Crawler** | Playwright, playwright-stealth |
| **Pipeline** | pandas, PyMuPDF, Apache Airflow |
| **Monitoring** | Prometheus, Grafana, AlertManager |
| **Infra** | Docker Compose, Nginx, Let's Encrypt |

---

## Yêu cầu hệ thống

### Cài đặt bằng Docker (khuyến nghị)

- Docker Desktop >= 4.x (hoặc Docker Engine + Compose v2)
- RAM: tối thiểu 8 GB (khuyến nghị 16 GB — model bge-m3 chiếm ~2.2 GB)
- Disk: ~5 GB trống (model cache + data)

### Cài đặt thủ công

- Python 3.12
- Node.js >= 20
- PostgreSQL 16 với extension `pgvector`
- Redis 7

---

## Cài đặt nhanh bằng Docker

### Bước 1 — Cấu hình môi trường

```bash
cp .env.example .env
```

Mở `.env` và điền 3 giá trị bắt buộc:

```env
GEMINI_API_KEY=your_gemini_api_key_here
AGENT_INTERNAL_KEY=some-random-secret-string
JWT_SECRET_KEY=another-random-secret-string
```

> Xem đầy đủ tại mục [Biến môi trường](#biến-môi-trường).

### Bước 2 — Tải model embedding (lần đầu)

Model `BAAI/bge-m3` (~2.2 GB) cần tải về host trước — container sẽ dùng chung cache:

```bash
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

> Cache tại `~/.cache/huggingface/` — đã được mount vào container trong `docker-compose.yml`.

### Bước 3 — Khởi động toàn bộ stack

```bash
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

### Bước 4 — Kiểm tra

```bash
docker compose ps
curl http://localhost:8000/api/v1/health
```

### Các service và port

| Service | Port | Mô tả |
|---|---|---|
| **Frontend** | `3000` | Next.js web app |
| **Backend API** | `8000` | FastAPI REST API + Swagger docs |
| **Agent Service** | `8100` | LangGraph multi-agent (internal only) |
| **Pipeline Worker** | `8200` | Crawl + ingest jobs (internal only) |
| **PostgreSQL** | `5432` | Database chính + pgvector |
| **Redis** | `6379` | Cache + session store |
| **Prometheus** | `9090` | Metrics collection |
| **Grafana** | `3001` | Dashboards (admin / admin) |
| **AlertManager** | `9093` | Cảnh báo → Slack |
| **Nginx** | `80` / `443` | Reverse proxy |

| URL | Mô tả |
|---|---|
| http://localhost:3000 | Frontend |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:3001 | Grafana (admin / admin) |

---

## Cài đặt thủ công (phát triển local)

Chạy theo đúng thứ tự: infra → agent-service → pipeline-worker → backend → frontend.

### Bước 1 — Khởi động infrastructure

```powershell
docker compose up -d postgres redis
```

### Bước 2 — Tạo virtual environment Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows
# source .venv/bin/activate          # Linux / macOS
pip install -r requirements.txt
cd backend && pip install -r requirements.txt && cd ..
```

### Bước 3 — Apply database migrations

```powershell
cd backend
alembic upgrade head
cd ..
```

### Bước 4 — Chạy Agent Service

Chạy từ **thư mục gốc** (để `agent_service.*` imports hoạt động):

```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend"
$env:AGENT_ALLOW_DEV_INTERNAL_KEY = "true"
uvicorn agent_service.main:app --reload --port 8100
```

### Bước 5 — Chạy Pipeline Worker

```powershell
$env:PYTHONPATH = "$PWD"
uvicorn pipeline_worker.main:app --reload --port 8200
```

### Bước 6 — Chạy Backend

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

### Bước 7 — Chạy Frontend

```powershell
cd frontend && npm install && npm run dev
```

Truy cập http://localhost:3000.

---

## Biến môi trường

Tất cả biến đọc từ file `.env` ở thư mục gốc. Xem chi tiết tại `backend/app/config.py` và `agent_service/config.py`.

### Bắt buộc

| Biến | Ý nghĩa |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key — thiếu thì router fallback sang rule-based |
| `AGENT_INTERNAL_KEY` | Khóa xác thực nội bộ backend ↔ agent-service |
| `JWT_SECRET_KEY` | Khóa ký JWT — **đổi khi deploy production** |

### Database & Cache

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://admin:realestate_secret_2026@localhost:5432/realestate` | SQLAlchemy async URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL |
| `POSTGRES_PASSWORD` | `realestate_secret_2026` | **Đổi khi deploy production** |

> Docker: host = `postgres` (tên service). Local: host = `localhost`.

### AI / Embedding

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model chatbot |
| `GEMINI_JUDGE_MODEL` | `gemini-2.5-flash` | Model LLM judge |
| `HF_EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model |
| `EMBEDDING_DIM` | `1024` | Số chiều vector — phải khớp pgvector schema |
| `CHATBOT_EMBEDDING_LOCAL_FILES_ONLY` | `true` | Không re-download model |
| `COHERE_API_KEY` | _(trống)_ | Bật Cohere reranker (tùy chọn) |

### Agent Service

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AGENT_ROUTER_MODE` | `hybrid` | `rule` / `llm` / `hybrid` |
| `AGENT_AGENTIC_MODE` | `true` | Bật ReAct tool loop |
| `AGENT_STREAM_ENABLED` | `true` | SSE streaming |
| `AGENT_CHECKPOINT_ENABLED` | `true` | Lưu graph state (SQLite) |
| `AGENT_ALLOW_DEV_INTERNAL_KEY` | `false` | Cho phép key mặc định khi dev local |
| `SLACK_WEBHOOK_URL` | _(trống)_ | Alert qua Slack (tùy chọn) |

---

## Cấu trúc dự án

```
RealEstate_Chatbot_v2/
├── agent_service/          # LangGraph multi-agent RAG service (:8100)
│   ├── agents/             # 6 specialist agents
│   ├── graph/              # StateGraph: supervisor → specialist → grade → rewrite → synthesize
│   ├── tools/              # Hybrid retrieval, market stats, readiness
│   ├── llm/                # Gemini wrapper + cost tracking
│   ├── evaluation/         # LLM-as-judge (5 metrics)
│   └── contracts.py        # AgentChatRequest/Response (mirror'd in backend)
│
├── backend/                # FastAPI public API (:8000)
│   ├── app/
│   │   ├── main.py         # Entrypoint
│   │   ├── models/         # ORM: User, Listing, Project, Article, Chunk, Chat...
│   │   ├── routers/        # auth, chat, listings, market, projects, articles, admin, metrics
│   │   └── services/       # agent_service client, chatbot orchestrator
│   └── alembic/            # Migrations
│
├── frontend/               # Next.js 16 App Router (:3000)
│   ├── app/                # /, /nha-dat-ban, /thi-truong, /dang-nhap, /admin
│   ├── components/         # ChatWidget, ListingCard, FilterPanel, AdminDashboard
│   └── lib/                # api.ts, types.ts
│
├── pipeline_worker/        # ETL service (:8200)
├── crawler/                # Playwright crawlers: sale, rent, projects, news
├── data_pipeline/          # clean → chunk → embed → ingest
├── airflow/                # Airflow DAGs (docker-compose riêng)
├── infra/                  # Prometheus, Grafana, AlertManager, Nginx configs
└── docker-compose.yml      # Full stack: 13 services
```

> `backend/main.py` là **legacy** — không dùng. Entrypoint chính là `backend/app/main.py`.

---

## Chatbot multi-agent RAG

### LangGraph StateGraph (kiến trúc hiện tại)

```
query
  │
  ▼
[supervisor] — phân tích intent, chọn agents, query rewriting
  │
  ├──► [specialist] — các agents chạy song song:
  │         property_search    · market_analysis  · legal_advisor
  │         investment_advisor · news_agent       · project_agent
  │
  ▼
[grade] — đánh giá chất lượng kết quả
  │
  ├── pass ──► [synthesize] — tổng hợp, committee review, safety check → response
  │
  └── fail ──► [rewrite] — viết lại query → quay lại [specialist]
```

Mỗi specialist có thể chạy **ReAct tool loop** (`AGENT_AGENTIC_MODE=true`) — tức là tự gọi tool, kiểm tra kết quả, gọi lại nếu cần, tối đa `AGENT_REACT_MAX_ITERATIONS=2` vòng.

Graph state được checkpoint vào SQLite (`AGENT_CHECKPOINT_PATH`). Streaming qua SSE — mỗi node emit một event.

### Hybrid Retrieval

1. **SQL filter** — lọc theo loại BĐS, giá, diện tích, khu vực
2. **Vector search** — pgvector kNN trên `chunks.embedding` (HNSW, cosine)
3. **Full-text search** — tsvector RRF trên `chunks.text_tsv` (unaccent Vietnamese)
4. **Rerank** — Cohere (nếu có key), fallback cosine
5. **Resolve** — map chunks → parent record (listing / project / article)

### Cấu hình

| Biến | Mặc định | Mô tả |
|---|---|---|
| `AGENT_ROUTER_MODE` | `hybrid` | `rule`: keyword, `llm`: Gemini, `hybrid`: kết hợp |
| `AGENT_REACT_MAX_ITERATIONS` | `2` | Số vòng ReAct tối đa mỗi specialist |
| `AGENT_LLM_MONTHLY_BUDGET_USD` | `100` | Ngưỡng cảnh báo chi phí LLM |

---

## Data Pipeline & Crawler

### Crawler

```powershell
# URLs
python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/sale_urls.csv --workers 4
# Details
python -m crawler.sale.crawl_details --input data/raw/sale_urls.csv --output data/raw/sale_details.csv --workers 4
# Tương tự: crawler.rent / crawler.projects / crawler.news
```

### Ingest

Pipeline: **clean → enrich → upsert → chunk → embed (bge-m3) → index pgvector**

```powershell
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_details.csv --batch-size 50
python -m data_pipeline.ingestors.projects_ingestor --csv data/raw/projects_details.csv --batch-size 25
python -m data_pipeline.ingestors.news_ingestor     --csv data/raw/news_articles.csv --batch-size 25
python -m data_pipeline.ingestors.legal_kb_ingestor
```

### Airflow (lên lịch tự động)

```powershell
docker compose up -d postgres redis backend   # tạo network trước
cd airflow && docker compose -f docker-compose.airflow.yml up -d --build
```

| DAG | Lịch | Mô tả |
|---|---|---|
| `daily_listings_dag` | 2:00 AM | Crawl + ingest sale/rent |
| `weekly_projects_dag` | CN 3:00 AM | Crawl + ingest dự án |
| `weekly_news_dag` | CN 4:00 AM | Crawl + ingest tin tức |
| `monthly_legal_kb_dag` | Ngày 1 5:00 AM | Re-ingest legal KB |

---

## Monitoring

Prometheus + Grafana + AlertManager. Truy cập http://localhost:3001 (admin / admin).

| Metric | Mô tả |
|---|---|
| `realestate_retrieval_latency_seconds` | Latency hybrid search (histogram) |
| `realestate_chat_requests_total` | Số chat request |
| `realestate_llm_cost_usd` | Chi phí LLM tháng hiện tại |
| `realestate_chunks_total` | Số chunks đã index |
| `realestate_pipeline_runs_total` | Pipeline runs theo DAG + status |

Alert: backend/postgres/redis DOWN (critical), P95 latency >2s, LLM budget exceeded, no chat traffic 15 phút (warning).

---

## API Backend

Tất cả endpoint dưới `/api/v1`. Xem đầy đủ tại http://localhost:8000/docs.

| Router | Prefix | Mô tả |
|---|---|---|
| `auth` | `/api/v1/auth` | Đăng ký, đăng nhập, JWT |
| `listings` | `/api/v1/listings` | CRUD, filter, sort, similar |
| `market` | `/api/v1/market` | Thống kê giá theo khu vực |
| `chat` | `/api/v1/chat` | Chatbot, sessions, history |
| `projects` | `/api/v1/projects` | Dự án BĐS |
| `articles` | `/api/v1/articles` | Tin tức, legal KB |
| `preferences` | `/api/v1/preferences` | User memory |
| `admin` | `/api/v1/admin` | Traces, eval runs, agent health |
| `metrics` | `/metrics` | Prometheus endpoint |

### Database — các bảng chính

| Bảng | Mô tả |
|---|---|
| `listings` / `projects` / `articles` | Dữ liệu BĐS |
| `chunks` | Semantic chunks + vector 1024-dim (HNSW) — canonical embedding store |
| `chat_sessions` / `chat_messages` | Lịch sử chat |
| `agent_traces` / `agent_llm_calls` / `agent_retrieval_events` | Observability |
| `eval_runs` / `eval_scores` | LLM judge |

```powershell
cd backend
alembic upgrade head                              # apply
alembic revision --autogenerate -m "description" # tạo mới
alembic heads                                     # kiểm tra sau khi merge branch
```

---

## Testing

```powershell
# Backend
cd backend && python -m pytest tests -q

# Agent service (từ thư mục gốc)
python -m pytest agent_service/tests -q

# Syntax check
python -m compileall backend/app agent_service pipeline_worker data_pipeline

# Frontend
cd frontend && npm run lint && npm run build
```

> Agent tests dùng httpx fake transport và LLM giả — không cần Gemini API key.

---

## Troubleshooting

| Vấn đề | Cách xử lý |
|---|---|
| Backend không kết nối DB | `DATABASE_URL` host: `localhost` (local) vs `postgres` (Docker) |
| `extension "vector" does not exist` | Dùng image `pgvector/pgvector:pg16`; chạy `CREATE EXTENSION IF NOT EXISTS vector;` |
| Chatbot không trả về sources | Kiểm tra bảng `chunks` có data, `EMBEDDING_DIM=1024`, model BGE-M3 đã cache |
| Agent Service không phản hồi | `curl -H "X-Internal-Agent-Key: dev-agent-internal-key" http://localhost:8100/internal/agent/health` |
| Agent Service import error | Chạy từ **thư mục gốc** với `PYTHONPATH="$PWD;$PWD\backend"` |
| Model BGE-M3 tải lại mỗi build | Tải model về host trước (bước 2), `docker-compose.yml` đã mount `~/.cache/huggingface` |
| Crawler bị block | Giảm `--workers`, kiểm tra CSS selector còn đúng không |
| Airflow không thấy network | Chạy `docker compose up -d` trước để tạo network |
| Alembic nhiều heads | `alembic merge heads -m "merge"` |

---

## Tài liệu thêm

- `docs/pipeline.md` — Thiết kế pipeline crawl/index
- `docs/multiagent-workflow.md` — Kiến trúc multi-agent
- `docs/guide_chay_datapipeline.md` — Hướng dẫn data pipeline
- `CLAUDE.md` — Hướng dẫn cho AI assistant
