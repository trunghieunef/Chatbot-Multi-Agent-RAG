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
- [Tính năng chatbot multi-agent RAG](#tính-năng-chatbot-multi-agent-rag)
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
         Backend (FastAPI :8000)        ← public API, auth, listings, chat orchestration
               │  POST /internal/agent/chat
               ▼
         Agent Service (FastAPI + LangGraph :8100)   ← multi-agent RAG (internal)
               │
         Pipeline Worker (FastAPI :8200)              ← crawl/embed/ingest (internal)
               │
         PostgreSQL 16 + pgvector  +  Redis 7
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
- RAM: tối thiểu 8 GB (khuyến nghị 16 GB vì mô hình bge-m3 ~2.2 GB)
- Disk: ~5 GB trống (model cache + data)

### Cài đặt thủ công

- Python >= 3.11
- Node.js >= 20
- PostgreSQL 16 với extension `pgvector`
- Redis 7

---

## Cài đặt nhanh bằng Docker

### Bước 1 — Cấu hình môi trường

```bash
cp .env.example .env   # Nếu chưa có .env
```

Mở `.env` và điền ít nhất các giá trị bắt buộc:

```env
GEMINI_API_KEY=your_gemini_api_key_here
AGENT_INTERNAL_KEY=some-random-secret-string
JWT_SECRET_KEY=another-random-secret-string
```

> Xem đầy đủ danh sách biến môi trường tại mục [Biến môi trường](#biến-môi-trường).

### Bước 2 — Tải model embedding (lần đầu)

Model `BAAI/bge-m3` (~2.2 GB) cần được tải về trước để container dùng chung cache:

```bash
pip install sentence-transformers
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

> Model sẽ được cache tại `~/.cache/huggingface/` và mount vào container tự động.

### Bước 3 — Khởi động toàn bộ stack

```bash
docker compose up -d --build
```

### Bước 4 — Apply database migrations

```bash
docker compose exec backend alembic upgrade head
```

### Bước 5 — Kiểm tra trạng thái

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

### URLs quan trọng

| URL | Mô tả |
|---|---|
| http://localhost:3000 | Frontend |
| http://localhost:8000/docs | Swagger UI (Backend) |
| http://localhost:8000/api/v1/health | Health check |
| http://localhost:3001 | Grafana dashboards |
| http://localhost:9090 | Prometheus UI |

---

## Cài đặt thủ công (phát triển local)

Cách này phù hợp khi cần debug hoặc phát triển từng service riêng lẻ. Chạy theo đúng thứ tự dưới đây.

### Bước 1 — Khởi động infrastructure

```powershell
docker compose up -d postgres redis
```

Đợi khoảng 10 giây rồi kiểm tra:

```powershell
docker compose ps postgres redis
```

### Bước 2 — Tạo virtual environment Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows PowerShell
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
cd backend && pip install -r requirements.txt && cd ..
```

### Bước 3 — Apply database migrations

```powershell
cd backend
alembic upgrade head
cd ..
```

> Nếu gặp lỗi `extension "vector" does not exist`, chạy:
> ```sql
> -- Kết nối vào PostgreSQL và chạy:
> CREATE EXTENSION IF NOT EXISTS vector;
> ```

### Bước 4 — Chạy Agent Service

Chạy từ **thư mục gốc** của repo (để import `agent_service.*` hoạt động):

```powershell
$env:PYTHONPATH = "$PWD;$PWD\backend"
$env:AGENT_ALLOW_DEV_INTERNAL_KEY = "true"
uvicorn agent_service.main:app --reload --port 8100
```

Kiểm tra:

```powershell
curl -H "X-Internal-Agent-Key: dev-agent-internal-key" http://localhost:8100/internal/agent/health
```

### Bước 5 — Chạy Pipeline Worker

Mở terminal mới (cũng từ thư mục gốc):

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

Mở terminal mới:

```powershell
cd frontend
npm install
npm run dev
```

Truy cập http://localhost:3000.

---

## Biến môi trường

Tất cả biến đọc từ file `.env` ở thư mục gốc. Xem chi tiết tại `backend/app/config.py` và `agent_service/config.py`.

### Bắt buộc

| Biến | Ý nghĩa |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key (LLM + judge). Không có thì chatbot fallback sang keyword routing |
| `AGENT_INTERNAL_KEY` | Khóa xác thực nội bộ giữa backend ↔ agent-service |
| `JWT_SECRET_KEY` | Khóa ký JWT. **Bắt buộc đổi khi deploy production** |

### Database & Cache

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://admin:realestate_secret_2026@localhost:5432/realestate` | SQLAlchemy async connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `POSTGRES_DB` | `realestate` | Tên database |
| `POSTGRES_USER` | `admin` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `realestate_secret_2026` | PostgreSQL password |

> Khi chạy Docker: host là `postgres` (tên service). Khi chạy local: host là `localhost`.

### AI / Embedding

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model Gemini cho chatbot |
| `GEMINI_JUDGE_MODEL` | `gemini-2.5-flash` | Model Gemini cho LLM judge |
| `HF_EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model (HuggingFace) |
| `EMBEDDING_DIM` | `1024` | Số chiều vector — phải khớp pgvector schema |
| `CHATBOT_EMBEDDING_LOCAL_FILES_ONLY` | `true` | Chạy offline (không tải lại model) |
| `COHERE_API_KEY` | _(trống)_ | Bật Cohere reranker (tùy chọn) |

### Agent Service

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `AGENT_SERVICE_URL` | `http://localhost:8100` | URL agent service (backend dùng) |
| `CHATBOT_AGENT_SERVICE_ENABLED` | `true` | Dùng agent service thay vì inline |
| `AGENT_ROUTER_MODE` | `hybrid` | Chế độ router: `rule` / `llm` / `hybrid` |
| `AGENT_AGENTIC_MODE` | `true` | Bật ReAct tool loop cho specialist agents |
| `AGENT_STREAM_ENABLED` | `true` | Bật SSE streaming |
| `AGENT_CHECKPOINT_ENABLED` | `true` | Lưu graph state vào SQLite |
| `AGENT_ALLOW_DEV_INTERNAL_KEY` | `false` | Cho phép dùng key mặc định khi dev local |

### Monitoring & Thông báo

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `SLACK_WEBHOOK_URL` | _(trống)_ | Nhận alert qua Slack (tùy chọn) |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin username |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Grafana admin password |

---

## Cấu trúc dự án

```
RealEstate_Chatbot_v2/
├── agent_service/          # Internal LangGraph multi-agent RAG service (:8100)
│   ├── main.py             # FastAPI entrypoint
│   ├── config.py           # Pydantic settings
│   ├── contracts.py        # AgentChatRequest/Response, Evidence, RetrievalTask
│   ├── agents/             # 6 specialist agents (property, market, legal, investment, news, project)
│   ├── graph/              # LangGraph StateGraph: router → dispatch → synthesize
│   ├── llm/                # Gemini wrapper + cost tracking
│   ├── tools/              # Hybrid retrieval, market stats, readiness snapshot
│   └── evaluation/         # LLM-as-judge (5 metrics)
│
├── backend/                # FastAPI v2 public API (:8000)
│   ├── app/
│   │   ├── main.py         # Entrypoint: uvicorn app.main:app
│   │   ├── config.py       # Settings từ .env
│   │   ├── database.py     # Async SQLAlchemy engine
│   │   ├── models/         # ORM: User, Listing, Project, Article, Chunk, Chat, PipelineRun
│   │   ├── routers/        # admin, auth, chat, listings, market, metrics, preferences, projects
│   │   └── services/       # agent_service client, chatbot orchestrator, hybrid search
│   ├── alembic/            # Database migrations
│   └── tests/              # Pytest suite
│
├── frontend/               # Next.js 16 App Router + React 19 + Tailwind CSS v4 (:3000)
│   ├── app/                # Pages: /, /nha-dat-ban, /thi-truong, /dang-nhap, /admin
│   ├── components/         # Layout, ListingCard, FilterPanel, ChatWidget, AdminDashboard
│   └── lib/                # api.ts, types.ts, utils.ts
│
├── pipeline_worker/        # Internal ETL service (:8200)
│   ├── main.py             # FastAPI: /internal/pipeline/*
│   ├── runner.py           # Chạy crawl modules
│   └── maintenance.py      # Cleanup, đánh dấu tin hết hạn
│
├── crawler/                # Playwright headless crawlers
│   ├── core/               # Parser helpers, CSV utils
│   ├── sale/               # Tin bán
│   ├── rent/               # Tin thuê
│   ├── projects/           # Dự án BĐS
│   └── news/               # Tin tức
│
├── data_pipeline/          # ETL: clean → chunk → embed → ingest
│   ├── ingestors/          # listings, projects, news, legal KB
│   └── legal/              # PDF/HTML legal parser
│
├── airflow/                # Airflow DAGs + docker-compose riêng
├── infra/                  # Prometheus, Grafana, AlertManager, Nginx configs
├── data/                   # CSV mẫu, knowledge base, raw crawl output
├── docs/                   # Architecture docs, implementation plans
├── docker-compose.yml      # Full stack: 13 services
└── .env                    # Biến môi trường (không commit)
```

> **Lưu ý:** `backend/main.py` là legacy (đọc CSV trực tiếp) — không dùng. Entrypoint chính là `backend/app/main.py`.
> Các thư mục `RAG/`, `Crawl/`, `FrontEnd_old/`, `batdongsancom-crawler/` là code cũ, chỉ để tham khảo.

---

## Tính năng chatbot multi-agent RAG

### Luồng xử lý

```
Query người dùng
    │
    ▼
[router] — Phân tích intent, chọn specialist agents
    │
    ▼
[dispatch_agents] — Các agents chạy song song (asyncio)
    ├── property_search   — Tìm BĐS theo tiêu chí
    ├── market_analysis   — Phân tích giá, xu hướng thị trường
    ├── legal_advisor     — Tư vấn pháp lý (kèm disclaimer)
    ├── investment_advisor — Phân tích đầu tư, ROI (kèm disclaimer)
    ├── news_agent        — Tin tức thị trường mới nhất
    └── project_agent     — Thông tin dự án BĐS
    │
    ▼
[synthesize] — Tổng hợp kết quả, committee review, safety check
    │
    ▼
Câu trả lời + danh sách evidence (có source)
```

### Hybrid Retrieval

1. **SQL filter** — Lọc candidates theo cấu trúc (loại BĐS, giá, diện tích, khu vực)
2. **Vector search** — pgvector kNN trên `chunks.embedding` (cosine distance, HNSW index)
3. **Rerank** — Cohere rerank (nếu có `COHERE_API_KEY`)
4. **Resolve** — Map chunks → parent records (listing / project / article)

### Cấu hình chatbot

| Flag | Mặc định | Mô tả |
|---|---|---|
| `AGENT_ROUTER_MODE` | `hybrid` | `rule`: keyword, `llm`: Gemini, `hybrid`: kết hợp |
| `AGENT_AGENTIC_MODE` | `true` | Bật ReAct tool loop |
| `AGENT_REACT_MAX_ITERATIONS` | `2` | Số vòng lặp ReAct tối đa |
| `AGENT_STREAM_ENABLED` | `true` | SSE streaming response |
| `AGENT_LLM_MONTHLY_BUDGET_USD` | `100` | Ngưỡng cảnh báo chi phí LLM |

---

## Data Pipeline & Crawler

### Crawler (Playwright)

Crawler dùng Playwright headless Chromium với stealth mode, retry, và parallel workers.

```powershell
# Crawl URLs tin bán
python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/sale_urls.csv --workers 4

# Crawl chi tiết từng tin
python -m crawler.sale.crawl_details --input data/raw/sale_urls.csv --output data/raw/sale_details.csv --workers 4 --limit 100

# Tương tự cho rent, projects, news
python -m crawler.rent.crawl_urls --pages 1 3 --output data/raw/rent_urls.csv
python -m crawler.projects.crawl_urls --pages 1 2 --output data/raw/project_urls.csv
python -m crawler.news.crawl_urls --pages 1 5 --output data/raw/news_urls.csv
```

### Ingest dữ liệu

Pipeline thực hiện: **clean → enrich → upsert parent → chunk → embed → index vào pgvector**

```powershell
# Ingest tin bán/thuê
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/sale_details.csv --batch-size 50

# Ingest dự án
python -m data_pipeline.ingestors.projects_ingestor --csv data/raw/projects_details.csv --batch-size 25

# Ingest tin tức
python -m data_pipeline.ingestors.news_ingestor --csv data/raw/news_articles.csv --batch-size 25

# Ingest legal knowledge base (từ PDF/HTML)
python -m data_pipeline.ingestors.legal_kb_ingestor
```

### Airflow (lên lịch tự động)

Airflow có `docker-compose` riêng trong `airflow/`.

```powershell
# Chạy app stack trước để tạo network
docker compose up -d postgres redis backend

# Chạy Airflow
cd airflow
docker compose -f docker-compose.airflow.yml up -d --build
```

Truy cập Airflow UI tại http://localhost:8080.

| DAG | Lịch | Mô tả |
|---|---|---|
| `daily_listings_dag` | 2:00 AM hàng ngày | Crawl + ingest sale/rent, đánh dấu tin hết hạn |
| `weekly_projects_dag` | 3:00 AM Chủ nhật | Crawl + ingest dự án |
| `weekly_news_dag` | 4:00 AM Chủ nhật | Crawl + ingest tin tức |
| `monthly_legal_kb_dag` | 5:00 AM ngày 1 | Re-ingest legal knowledge base |

---

## Monitoring

Stack gồm **Prometheus + Grafana + AlertManager**.

### Metrics

| Metric | Mô tả |
|---|---|
| `realestate_chat_requests_total` | Số chat request |
| `realestate_retrieval_latency_seconds` | Latency hybrid search (histogram) |
| `realestate_listings_total` | Số tin đăng theo loại |
| `realestate_chunks_total` | Số chunks đã index |
| `realestate_pipeline_runs_total` | Pipeline runs theo DAG + status |
| `realestate_llm_cost_usd` | Chi phí LLM tháng hiện tại |

### Alert rules

| Cảnh báo | Mức độ |
|---|---|
| Backend / PostgreSQL / Redis DOWN | Critical |
| Không có chat traffic trong 15 phút | Warning |
| P95 retrieval latency > 2s | Warning |
| Pipeline DAG fail liên tục | Warning |
| LLM monthly budget exceeded | Warning |
| PostgreSQL > 50 connections | Warning |
| Redis memory > 85% | Warning |

Truy cập Grafana tại http://localhost:3001 (admin / admin).

---

## API Backend

Tất cả endpoint được mount tại `/api/v1`. Xem đầy đủ tại http://localhost:8000/docs.

| Router | Prefix | Mô tả |
|---|---|---|
| `auth` | `/api/v1/auth` | Đăng ký, đăng nhập, JWT |
| `listings` | `/api/v1/listings` | CRUD tin đăng, filter, sort, similar |
| `market` | `/api/v1/market` | Thống kê thị trường, giá theo khu vực |
| `chat` | `/api/v1/chat` | Chatbot multi-agent, sessions, history |
| `preferences` | `/api/v1/preferences` | User preferences & memory |
| `projects` | `/api/v1/projects` | Dự án BĐS |
| `articles` | `/api/v1/articles` | Tin tức, legal KB |
| `admin` | `/api/v1/admin` | Traces, eval runs, agent health |
| `metrics` | `/metrics` | Prometheus exposition endpoint |

---

## Database

PostgreSQL 16 + pgvector extension.

### Các bảng chính

| Bảng | Mô tả |
|---|---|
| `users` | Tài khoản người dùng |
| `listings` | Tin bán / thuê |
| `projects` | Dự án BĐS |
| `articles` | Tin tức + legal knowledge base |
| `chunks` | Semantic chunks + vector embedding 1024-dim (HNSW index) |
| `chat_sessions` / `chat_messages` | Lịch sử chat |
| `pipeline_runs` | Log các lần chạy pipeline |
| `agent_traces` / `agent_trace_steps` | Observability traces |
| `eval_runs` / `eval_scores` | LLM judge evaluation |

### Quản lý migration

```powershell
cd backend

# Apply tất cả migration
alembic upgrade head

# Tạo migration mới
alembic revision --autogenerate -m "mo_ta_ngan_gon"

# Kiểm tra trạng thái
alembic current
alembic heads
```

> Không chỉnh sửa migration đã tồn tại. Luôn tạo file mới với format `YYYYMMDD_NNNN_description.py`.

---

## Testing

```powershell
# Backend tests
cd backend && python -m pytest tests -q

# Agent service tests (chạy từ thư mục gốc)
python -m pytest agent_service/tests -q

# Test một file cụ thể
python -m pytest agent_service/tests/test_synthesis.py -q

# Kiểm tra syntax Python
python -m compileall backend/app agent_service pipeline_worker data_pipeline

# Frontend
cd frontend && npm run lint
cd frontend && npm run build
```

> Agent tests dùng httpx fake transport và LLM giả — không cần Gemini API key hay service thật.

---

## Troubleshooting

| Vấn đề | Cách xử lý |
|---|---|
| Backend không kết nối DB | `DATABASE_URL`: local dùng `localhost`, trong Docker dùng `postgres` (tên service) |
| `extension "vector" does not exist` | Dùng image `pgvector/pgvector:pg16`; chạy `CREATE EXTENSION IF NOT EXISTS vector;` |
| Chatbot không trả về sources | Kiểm tra bảng `chunks` có data; `EMBEDDING_DIM=1024`; model BGE-M3 đã tải về cache |
| Agent Service không phản hồi | `curl -H "X-Internal-Agent-Key: $AGENT_INTERNAL_KEY" http://localhost:8100/internal/agent/health` |
| Frontend gọi API bị lỗi | Kiểm tra backend health; đảm bảo `INTERNAL_API_URL` đúng host |
| Crawler bị block / timeout | Giảm `--workers`, thêm delay, kiểm tra CSS selector còn đúng không |
| Model BGE-M3 tải lại mỗi lần build | Mount `~/.cache/huggingface` vào container (đã cấu hình trong `docker-compose.yml`) |
| Airflow không thấy network | Chạy `docker compose up -d` trước để tạo network `realestate_chatbot_v2_default` |
| `AGENT_ALLOW_DEV_INTERNAL_KEY` cần bật | Thêm `$env:AGENT_ALLOW_DEV_INTERNAL_KEY="true"` khi chạy agent-service local |
| Alembic báo nhiều heads | Chạy `alembic heads` rồi tạo merge migration: `alembic merge heads -m "merge"` |

---

## Tài liệu thêm

- `docs/pipeline.md` — Thiết kế pipeline crawl/index
- `docs/multiagent-workflow.md` — Kiến trúc multi-agent
- `docs/guide_chay_datapipeline.md` — Hướng dẫn data pipeline
- `.claude/rules/` — Coding conventions
- `CLAUDE.md` — Hướng dẫn cho AI assistant
