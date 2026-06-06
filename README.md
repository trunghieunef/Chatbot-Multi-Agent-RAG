# RealEstate Chatbot v2

Nền tảng tìm kiếm, phân tích và tư vấn bất động sản Việt Nam, gồm web frontend, FastAPI backend, PostgreSQL + pgvector, Redis cache, pipeline crawl/index dữ liệu và chatbot multi-agent RAG.

Dự án này không chỉ hiển thị tin đăng bất động sản. Codebase đang hướng tới một hệ thống end-to-end:

- Crawl tin bán, tin thuê, dự án và tin tức từ batdongsan.com.vn.
- Làm sạch, làm giàu, upsert dữ liệu vào PostgreSQL.
- Tạo semantic chunks, embedding bằng BGE-M3 và lưu vào pgvector.
- Truy vấn hybrid: SQL filter -> vector search -> rerank.
- Phục vụ UI Next.js, API FastAPI, dashboard thị trường và chatbot tư vấn.
- Lên lịch pipeline bằng Airflow và xuất metric Prometheus.

## Mục Lục

- [Kiến trúc tổng quan](#kiến-trúc-tổng-quan)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Công nghệ chính](#công-nghệ-chính)
- [Chạy nhanh bằng Docker Compose](#chạy-nhanh-bằng-docker-compose)
- [Chạy local để phát triển](#chạy-local-để-phát-triển)
- [Biến môi trường](#biến-môi-trường)
- [Backend API](#backend-api)
- [Frontend](#frontend)
- [Chatbot multi-agent RAG](#chatbot-multi-agent-rag)
- [Pipeline dữ liệu](#pipeline-dữ-liệu)
- [Crawler](#crawler)
- [Airflow](#airflow)
- [Database và migrations](#database-và-migrations)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Kiến Trúc Tổng Quan

```mermaid
flowchart TD
    User["Người dùng"] --> Frontend["Next.js frontend<br/>localhost:3000"]
    Frontend --> API["FastAPI backend<br/>localhost:8000"]

    API --> Postgres["PostgreSQL 16 + pgvector"]
    API --> Redis["Redis cache"]
    API --> Chat["Multi-agent chatbot"]

    Chat --> Router["Intent router"]
    Router --> Property["Property Search Agent"]
    Router --> Market["Market Analysis Agent"]
    Router --> Legal["Legal Advisor Agent"]
    Router --> Investment["Investment Advisor Agent"]

    Property --> Hybrid["Hybrid search"]
    Market --> Hybrid
    Legal --> Hybrid
    Investment --> Hybrid

    Hybrid --> SQL["SQL structured filters"]
    Hybrid --> Vector["pgvector kNN over chunks"]
    Hybrid --> Rerank["Cohere rerank, optional"]

    Crawler["Playwright crawlers"] --> CSV["CSV artifacts"]
    CSV --> Pipeline["data_pipeline ingestors"]
    Pipeline --> Postgres

    Airflow["Airflow DAGs"] --> Crawler
    Airflow --> Pipeline
```

Luồng dữ liệu chính:

1. Crawler tạo CSV thô trong `data/raw/` hoặc các file dữ liệu tương đương.
2. Ingestor chuyển row CSV thành parent rows có cấu trúc trong `listings`, `projects`, `articles`.
3. Ingestor tạo semantic chunks và embedding 1024 chiều trong bảng `chunks`.
4. UI đọc dữ liệu có cấu trúc từ API.
5. Chatbot đọc cả dữ liệu có cấu trúc và vector chunks qua hybrid retrieval.

Một quyết định quan trọng trong codebase là "publish trước, index sau": dữ liệu được upsert vào parent tables trước để UI/API nhìn thấy ngay, sau đó mới embed/index cho chatbot. Nếu embedding hoặc rerank lỗi, web vẫn có thể hiển thị dữ liệu đã crawl.

## Cấu Trúc Thư Mục

```text
RealEstate_Chatbot_v2/
├── backend/                  # FastAPI v2, SQLAlchemy models, routers, migrations, tests
│   ├── app/
│   │   ├── main.py            # Entrypoint API v2: app.main:app
│   │   ├── config.py          # Pydantic settings từ env/.env
│   │   ├── database.py        # Async SQLAlchemy engine/session
│   │   ├── models/            # User, Listing, Project, Article, Chunk, Chat, PipelineRun
│   │   ├── routers/           # auth, listings, market, chat, metrics
│   │   └── services/          # RAG, chatbot, listing scope
│   ├── alembic/               # Alembic migrations
│   └── tests/                 # Pytest suite
├── frontend/                 # Next.js 16 + React 19 + Tailwind CSS
│   ├── app/                   # App Router pages
│   ├── components/            # Layout, listing cards/grid, filters, chatbot widget
│   └── lib/                   # API client and shared TypeScript types
├── crawler/                  # Refactored Playwright crawlers
│   ├── core/                  # Parser and CSV helpers
│   ├── sale/                  # Tin bán
│   ├── rent/                  # Tin thuê
│   ├── projects/              # Dự án
│   └── news/                  # Tin tức/bài viết
├── data_pipeline/            # Clean, enrich, chunk, embed, ingest
│   ├── ingestors/             # listings, projects, news, legal KB ingestors
│   └── legal/                 # PDF/HTML legal parser and chunker
├── airflow/                  # Airflow DAGs, plugins, Docker setup
├── chatbot/                  # Legacy/standalone multi-agent scaffold
├── data/                     # CSV samples and knowledge-base input folders
├── docs/                     # Architecture and implementation plans
├── infra/                    # Grafana dashboard
├── docker-compose.yml        # App stack: postgres, redis, backend, frontend
└── requirements.txt          # Root Python dependencies for pipeline/dev
```

Lưu ý: `backend/main.py` là app demo/legacy đọc CSV và serve frontend tĩnh qua `/api/*`. Entrypoint chính của hệ thống v2 là `backend/app/main.py` với lệnh `uvicorn app.main:app`.

## Công Nghệ Chính

Backend:

- FastAPI, Uvicorn
- SQLAlchemy async, asyncpg
- Alembic
- PostgreSQL 16 + pgvector
- Redis
- PyJWT, bcrypt
- Prometheus client

AI/RAG:

- `sentence-transformers`
- BGE-M3: `BAAI/bge-m3`
- pgvector HNSW index
- Cohere rerank API, optional
- Google Gemini API, optional cho routing/intent extraction

Frontend:

- Next.js 16 App Router
- React 19
- TypeScript
- Tailwind CSS 4
- lucide-react
- Recharts

Data pipeline:

- Playwright + playwright-stealth
- pandas/numpy
- PyMuPDF cho legal PDF
- Airflow LocalExecutor

## Chạy Nhanh Bằng Docker Compose

Yêu cầu:

- Docker Desktop hoặc Docker Engine có Compose v2.
- Máy đủ RAM cho backend tải model embedding BGE-M3 khi cần chatbot/RAG.

Tạo `.env` ở root. File `.env` hiện được `docker-compose.yml` nạp vào backend. Ví dụ tối thiểu:

```env
POSTGRES_DB=realestate
POSTGRES_USER=admin
POSTGRES_PASSWORD=realestate_secret_2026
POSTGRES_PORT=5432
BACKEND_PORT=8000

DATABASE_URL=postgresql+asyncpg://admin:realestate_secret_2026@localhost:5432/realestate
REDIS_URL=redis://localhost:6379/0

JWT_SECRET_KEY=change-me-in-development
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

GEMINI_API_KEY=
COHERE_API_KEY=
HF_EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIM=1024
```

Chạy toàn bộ app:

```powershell
docker compose up --build
```

Các URL chính:

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/v1/health
- Backend docs: http://localhost:8000/docs
- Prometheus metrics: http://localhost:8000/metrics

Trong Docker Compose:

- `postgres` dùng image `pgvector/pgvector:pg16`.
- `redis` dùng `redis:7-alpine`.
- `backend` chạy `alembic upgrade head` rồi `uvicorn app.main:app --reload`.
- `frontend` chạy Next dev server, proxy `/api/v1/*` về backend service qua `INTERNAL_API_URL`.

## Chạy Local Để Phát Triển

Bạn có thể chạy Postgres/Redis bằng Docker và chạy backend/frontend trực tiếp trên máy.

### 1. Chạy database và cache

```powershell
docker compose up -d postgres redis
```

### 2. Cài Python dependencies

Root `requirements.txt` bao gồm backend, crawler, pipeline và AI dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu chỉ phát triển backend API:

```powershell
pip install -r backend\requirements.txt
```

### 3. Chạy migrations

```powershell
cd backend
alembic upgrade head
cd ..
```

`backend/app/main.py` cũng gọi `init_db()` khi startup để tạo bảng trong môi trường dev, nhưng production/dev nghiêm túc nên dùng Alembic để schema nhất quán.

### 4. Chạy backend

```powershell
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Chạy frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend mặc định gọi `NEXT_PUBLIC_API_URL=/api/v1`. `frontend/next.config.ts` rewrite `/api/v1/:path*` về `INTERNAL_API_URL` hoặc `http://localhost:8000`.

Khi chạy local, nếu cần chỉ định rõ:

```powershell
$env:INTERNAL_API_URL="http://localhost:8000"
$env:NEXT_PUBLIC_API_URL="/api/v1"
npm run dev
```

## Biến Môi Trường

Các settings chính nằm trong `backend/app/config.py`.

| Biến | Mặc định | Ý nghĩa |
|---|---:|---|
| `APP_NAME` | `Real Estate Chatbot API` | Tên app trong FastAPI docs |
| `APP_VERSION` | `2.0.0` | Version trả về ở health endpoint |
| `DEBUG` | `True` | Bật SQL echo; set `production`/`prod` để tắt |
| `DATABASE_URL` | local Postgres | SQLAlchemy async URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache query embedding/rerank |
| `JWT_SECRET_KEY` | demo secret | Secret ký JWT, cần đổi khi deploy |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Thời gian sống access token |
| `CORS_ORIGINS` | localhost frontend | Danh sách origin cách nhau bằng dấu phẩy |
| `GEMINI_API_KEY` | rỗng | Bật Gemini routing/intent khi có key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Model Gemini cho chatbot router |
| `GEMINI_INTENT_MODEL` | `gemini-2.0-flash` | Model Gemini cho intent tags |
| `EMBEDDING_PROVIDER` | `bge_m3` | Provider embedding hiện tại |
| `HF_EMBEDDING_MODEL` | `BAAI/bge-m3` | SentenceTransformer model |
| `EMBEDDING_DIM` | `1024` | Phải khớp `chunks.embedding vector(1024)` |
| `EMBEDDING_BATCH_SIZE` | `16` | Batch size embedding |
| `HF_EMBEDDING_DEVICE` | rỗng | Có thể set `cpu`, `cuda`, ... |
| `COHERE_API_KEY` | rỗng | Bật rerank khi có key |
| `RERANK_PROVIDER` | `cohere` | Provider rerank |
| `RERANK_MODEL` | `rerank-multilingual-v3.0` | Model rerank |
| `RERANK_TOP_N` | `5` | Số kết quả sau rerank |
| `GEOCODER_PROVIDER` | `nominatim` | `nominatim` hoặc `goong` |
| `GEOCODER_USER_AGENT` | demo UA | Bắt buộc tử tế khi dùng Nominatim |
| `GEOCODER_RATE_LIMIT_SECONDS` | `1.0` | Rate limit geocoding |
| `GOONG_API_KEY` | rỗng | Dự phòng cho Goong provider |
| `INTENT_EXTRACTOR` | `rule` | `rule` hoặc `gemini` |

Airflow dùng thêm:

| Biến | Ý nghĩa |
|---|---|
| `AIRFLOW_FERNET_KEY` | Bắt buộc cho Airflow secrets |
| `SLACK_WEBHOOK_URL` | Optional alert khi DAG fail |
| `ALERT_EMAIL_RECIPIENTS` | Optional email alert |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_PORT` | Optional SMTP alert |

## Backend API

Entrypoint chính:

```text
backend/app/main.py -> app.main:app
```

Routers được mount với prefix `/api/v1`.

### System

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/` | Thông tin cơ bản và link docs |
| `GET` | `/api/v1/health` | Health check |
| `GET` | `/metrics` | Prometheus exposition, không hiện trong OpenAPI |
| `GET` | `/api/v1/health/pipeline` | Tóm tắt tình trạng pipeline runs |

### Listings

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/listings` | Danh sách phân trang, filter và sort |
| `GET` | `/api/v1/listings/{listing_id}` | Chi tiết tin theo ID |
| `GET` | `/api/v1/listings/by-product-id/{product_id}` | Chi tiết theo ID gốc từ nguồn crawl |
| `GET` | `/api/v1/listings/similar/{listing_id}` | Tin tương tự cùng khu vực/loại/giá |

Query params tiêu biểu cho `/api/v1/listings`:

- `search`
- `listing_type`: `sale` hoặc `rent`
- `property_type`
- `city`, `district`
- `min_price`, `max_price`
- `min_area`, `max_area`
- `bedrooms`, `bathrooms`
- `direction`
- `sort`: `newest`, `price_asc`, `price_desc`, `area_asc`, `area_desc`
- `page`, `limit`

API listings đang dùng `app.services.listing_scope` để chỉ lấy scope public/latest, giới hạn bằng `PUBLIC_LISTING_LIMIT` và loại tin hết hạn/không active.

### Market

| Method | Path | Mô tả |
|---|---|---|
| `GET` | `/api/v1/market/stats` | Tổng số tin, giá/diện tích trung bình, sale/rent count |
| `GET` | `/api/v1/market/top-locations` | Top quận/huyện nhiều tin |
| `GET` | `/api/v1/market/price-by-district` | Giá theo quận/huyện |
| `GET` | `/api/v1/market/property-types` | Phân bổ loại hình BĐS |
| `GET` | `/api/v1/market/categories` | Danh sách property type |
| `GET` | `/api/v1/market/cities` | Thành phố kèm số tin |
| `GET` | `/api/v1/market/districts` | Quận/huyện, optional filter theo city |

### Auth

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Tạo user và trả JWT |
| `POST` | `/api/v1/auth/login` | Đăng nhập và trả JWT |
| `GET` | `/api/v1/auth/me` | Lấy profile user hiện tại |

Auth dùng JWT Bearer token. Password được hash bằng bcrypt.

### Chat

| Method | Path | Mô tả |
|---|---|---|
| `POST` | `/api/v1/chat` | Gửi message tới chatbot multi-agent |
| `GET` | `/api/v1/chat/sessions` | Lấy sessions của user đã đăng nhập |
| `GET` | `/api/v1/chat/sessions/{session_id}` | Lấy lịch sử một session |

Request tối thiểu:

```json
{
  "message": "Tìm căn hộ 2 phòng ngủ ở Quận 7 dưới 5 tỷ"
}
```

Response gồm:

- `session_id`
- `content`
- `agent_used`
- `sources`
- `suggested_actions`
- `created_at`

## Frontend

Frontend nằm trong `frontend/` và dùng Next.js App Router.

Các route chính:

| Route | File | Mô tả |
|---|---|---|
| `/` | `frontend/app/page.tsx` | Trang chủ, hero search, stats, featured listings |
| `/nha-dat-ban` | `frontend/app/nha-dat-ban/page.tsx` | Listing sale với filters/sort/pagination |
| `/nha-dat-cho-thue` | `frontend/app/nha-dat-cho-thue/page.tsx` | Listing rent |
| `/nha-dat-ban/[id]` | `frontend/app/nha-dat-ban/[id]/page.tsx` | Chi tiết listing |
| `/thi-truong` | `frontend/app/thi-truong/page.tsx` | Dashboard market charts |
| `/dang-nhap` | `frontend/app/dang-nhap/page.tsx` | Login |
| `/dang-ky` | `frontend/app/dang-ky/page.tsx` | Register |

API client tập trung ở `frontend/lib/api.ts`, TypeScript contracts ở `frontend/lib/types.ts`.

Các component chính:

- `components/layout/Header.tsx`
- `components/layout/Footer.tsx`
- `components/listing/ListingCard.tsx`
- `components/listing/ListingGrid.tsx`
- `components/search/FilterPanel.tsx`
- `components/chatbot/ChatWidget.tsx`

## Chatbot Multi-Agent RAG

Pipeline production nằm ở `backend/app/services/chatbot/`.

Luồng xử lý:

1. `routers/chat.py` nhận message và tạo/tìm `ChatSession`.
2. `run_chat_pipeline()` trong `orchestrator.py` gọi `route_query()`.
3. Router chọn một hoặc nhiều agent:
   - `property_search`
   - `market_analysis`
   - `legal_advisor`
   - `investment_advisor`
4. Các agent chạy song song bằng `asyncio.gather`.
5. Orchestrator gom kết quả, sources và suggested actions.
6. User/assistant messages được lưu vào DB.

Routing:

- Nếu không có `GEMINI_API_KEY`, router dùng keyword rules tiếng Việt không dấu.
- Nếu có `GEMINI_API_KEY`, router thử Gemini JSON classification; lỗi thì fallback keyword rules.

Retrieval:

- `backend/app/services/rag/hybrid_search.py`
- Stage 1: SQL filter lấy candidate parent IDs.
- Stage 2: embed query bằng BGE-M3.
- Stage 3: tìm chunks gần nhất bằng pgvector cosine distance.
- Stage 4: rerank bằng Cohere nếu có `COHERE_API_KEY`.
- Stage 5: resolve chunks về listing/project/article records.

Redis cache:

- Cache query embeddings trong namespace `embed:q`.
- Cache rerank result trong namespace `rerank`.
- Nếu Redis lỗi, retrieval vẫn fallback không cache.

## Pipeline Dữ Liệu

Pipeline nằm trong `data_pipeline/`.

### Listing ingestion

Entrypoint:

```powershell
python -m data_pipeline.ingestors.listings_ingestor --csv data\raw\sale_details.csv --batch-size 50
```

Các bước:

1. Đọc CSV bằng UTF-8-SIG.
2. `row_to_listing()` parse price, area, phòng ngủ, loại giao dịch, loại BĐS, vị trí.
3. Optional geocode bằng Nominatim.
4. Optional intent tags bằng Gemini nếu `INTENT_EXTRACTOR=gemini`.
5. Upsert `Listing` theo `product_id`.
6. Build chunks: `overview`, `description`, `location`, `intent_tags`.
7. Embed chunks bằng BGE-M3.
8. Xóa chunks cũ của listing và insert chunks mới.

Kết quả trả về dạng:

```json
{
  "published": 10,
  "indexed": 10,
  "chunks": 34,
  "publish_errors": 0,
  "index_errors": 0
}
```

### Project ingestion

```powershell
python -m data_pipeline.ingestors.projects_ingestor --csv data\raw\projects_details.csv --batch-size 25
```

Upsert theo `slug`, lưu vào `projects`, tạo chunks `overview`, `description`, `amenities`.

### News ingestion

```powershell
python -m data_pipeline.ingestors.news_ingestor --csv data\raw\news_articles.csv --batch-size 25
```

Upsert theo `url`, lưu vào `articles`, chunk title/body theo cửa sổ overlap.

### Legal knowledge base

Input mặc định:

```text
data/knowledge/raw/
```

Chạy:

```powershell
python -m data_pipeline.ingestors.legal_kb_ingestor
```

Pipeline legal:

- Đọc PDF/HTML.
- Tính SHA-256 để skip file đã ingest.
- Parse văn bản pháp lý.
- Chia theo cấu trúc chương/điều/khoản/điểm.
- Lưu parent `Article` với `category=legal`.
- Lưu citation metadata trong từng chunk để Legal Advisor trích dẫn.

## Crawler

Crawler mới nằm trong `crawler/`, dùng Playwright headless Chromium và stealth.

### Crawl sale URLs

```powershell
python -m crawler.sale.crawl_urls --pages 1 5 --output data\raw\sale_urls.csv --workers 4
```

### Crawl sale details

```powershell
python -m crawler.sale.crawl_details --input data\raw\sale_urls.csv --output data\raw\sale_details.csv --workers 4 --limit 100
```

### Crawl rent

```powershell
python -m crawler.rent.crawl_urls --pages 1 5 --output data\raw\rent_urls.csv --workers 4
python -m crawler.rent.crawl_details --input data\raw\rent_urls.csv --output data\raw\rent_details.csv --workers 4
```

### Crawl projects/news

```powershell
python -m crawler.projects.crawl_urls --pages 1 5 --output data\raw\projects_urls.csv --workers 3
python -m crawler.projects.crawl_details --input data\raw\projects_urls.csv --output data\raw\projects_details.csv --workers 3

python -m crawler.news.crawl_articles --pages 1 5 --output data\raw\news_articles.csv --workers 2
```

Các crawler có các đặc điểm chung:

- Worker song song.
- File tạm `.worker*.tmp`.
- Merge và dedupe cuối run.
- Resume bằng `product_id`.
- Browser restart định kỳ để giảm memory leak.
- `--since YYYY-MM-DD` ở detail crawler để giữ row mới hơn ngày chỉ định khi parse được `post_date`.

## Airflow

Airflow nằm trong `airflow/` và có compose riêng.

Các DAG:

| DAG | Lịch | Mô tả |
|---|---|---|
| `daily_listings_dag` | `0 2 * * *` | Crawl sale/rent, ingest listings, mark inactive expired listings |
| `weekly_projects_dag` | `0 3 * * 0` | Crawl và ingest projects |
| `weekly_news_dag` | `0 4 * * 0` | Crawl và ingest news |
| `monthly_legal_kb_dag` | `0 5 1 * *` | Re-ingest legal KB |

Chạy Airflow sau khi app stack đã có network:

```powershell
docker compose up -d postgres redis backend
cd airflow
docker compose -f docker-compose.airflow.yml up --build
```

Airflow UI:

```text
http://localhost:8080
username: admin
password: admin
```

Cần tạo Airflow connection `realestate_app` trong Admin -> Connections, trỏ tới app Postgres. DAG `daily_listings_dag` dùng connection này để chạy task `mark_active`.

Airflow compose mount toàn repo vào `/opt/project`, set:

```text
PYTHONPATH=/opt/project:/opt/project/backend
DATABASE_URL=postgresql+asyncpg://admin:<password>@realestate_postgres:5432/realestate
```

## Database Và Migrations

Database chính là PostgreSQL 16 với extension `vector`.

Các bảng nghiệp vụ chính:

| Bảng | Mô tả |
|---|---|
| `users` | User đăng nhập |
| `listings` | Tin bán/thuê từ crawler |
| `projects` | Dự án BĐS |
| `articles` | Tin tức và legal KB |
| `chunks` | Semantic chunks có vector embedding |
| `chat_sessions` | Chat sessions |
| `chat_messages` | Chat messages |
| `pipeline_runs` | Summary run của Airflow/pipeline |

Chạy migration:

```powershell
cd backend
alembic upgrade head
```

Tạo migration mới sau khi sửa models:

```powershell
cd backend
alembic revision --autogenerate -m "describe change"
```

Lưu ý quan trọng:

- `chunks.embedding` hiện là `vector(1024)`.
- BGE-M3 cũng trả vector 1024 chiều.
- Nếu đổi embedding model/dimension, cần migration và re-ingest toàn bộ chunks.
- Migration `20260801_0007_bge_m3_embeddings.py` đã chuyển chunks sang BGE-M3 1024 chiều và yêu cầu re-ingest.

## Testing

Backend tests:

```powershell
pytest backend\tests
```

Chạy một test cụ thể:

```powershell
pytest backend\tests\test_chat_router_pipeline.py -v
```

Frontend lint:

```powershell
cd frontend
npm run lint
```

Frontend build:

```powershell
cd frontend
npm run build
```

Một số nhóm test đáng chú ý:

- Crawler parsers: `test_listing_detail_parser.py`, `test_project_crawler_parsers.py`, `test_news_crawler_parsers.py`
- Data pipeline: `test_clean.py`, `test_chunk.py`, `test_embed.py`, `test_listings_ingestor.py`
- RAG: `test_hybrid_search.py`, `test_hybrid_search_caching.py`, `test_backend_hybrid_search.py`
- Chatbot: `test_chat_router_pipeline.py`, `test_production_chatbot.py`
- Airflow/pipeline: `test_dag_structure.py`, `test_pipeline_runner.py`, `test_run_metrics.py`
- Frontend/API contract: `test_frontend_data_performance.py`, `test_frontend_docker_config.py`

## Quy Trình Phát Triển Gợi Ý

1. Chạy `git status --short` trước khi sửa vì repo có thể đang có thay đổi dở.
2. Chạy Postgres/Redis bằng Docker.
3. Chạy backend local bằng `uvicorn app.main:app`.
4. Chạy frontend local bằng `npm run dev`.
5. Với thay đổi schema: thêm migration Alembic, chạy `alembic upgrade head`, chạy test liên quan.
6. Với thay đổi pipeline: test trên CSV nhỏ bằng `--limit` hoặc batch nhỏ trước khi chạy crawler lớn.
7. Với thay đổi RAG: re-ingest sample data nếu ảnh hưởng chunk/embedding.
8. Với thay đổi frontend: kiểm tra các route chính và chạy `npm run lint`.

## Troubleshooting

### Backend không kết nối được DB

Kiểm tra `DATABASE_URL` đang dùng host nào:

- Chạy backend local: thường là `localhost:5432`.
- Chạy backend trong Docker: phải là `postgres:5432`.
- Chạy Airflow container: app DB là `realestate_postgres:5432`.

### Lỗi `extension "vector" does not exist`

Đảm bảo Postgres dùng image:

```text
pgvector/pgvector:pg16
```

Sau đó chạy lại migration hoặc startup backend để tạo extension:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Chatbot không trả source

Kiểm tra:

1. Parent rows có trong `listings`, `projects` hoặc `articles`.
2. Chunks đã được tạo:

```sql
SELECT parent_type, count(*) FROM chunks GROUP BY parent_type;
```

3. `EMBEDDING_DIM` khớp schema.
4. Backend có đủ RAM để tải `BAAI/bge-m3`.
5. Redis/Cohere lỗi không nên làm fail retrieval, nhưng logs sẽ có warning fallback.

### Frontend gọi API lỗi

Kiểm tra:

- Backend health: `http://localhost:8000/api/v1/health`
- `frontend/next.config.ts` rewrite `/api/v1/:path*`.
- Khi chạy Docker, `INTERNAL_API_URL=http://backend:8000`.
- Khi chạy local, `INTERNAL_API_URL=http://localhost:8000`.

### Crawler bị block hoặc trả trang rỗng

Crawler đã có retry, stealth, delay ngẫu nhiên và browser restart. Nếu vẫn lỗi:

- Giảm `--workers`.
- Giảm page range.
- Dùng `--limit` khi crawl details.
- Kiểm tra selector trong fixture/test parser vì DOM site có thể thay đổi.

### Airflow không thấy app Postgres

Airflow compose dùng external network:

```text
realestate_chatbot_v2_default
```

Hãy chạy app compose trước để network tồn tại:

```powershell
docker compose up -d postgres redis backend
```

Sau đó chạy Airflow compose trong thư mục `airflow/`.

## Tài Liệu Liên Quan

- `docs/pipeline.md`: thiết kế pipeline crawl/index.
- `docs/multiagent-workflow.md`: workflow multi-agent.
- `docs/superpowers/plans/`: các implementation plans theo milestone.
- `guide_chay_datapipeline.md`: hướng dẫn chạy data pipeline bằng tiếng Việt.
- `frontend/README.md`: README mặc định của Next.js, hiện chưa phản ánh toàn bộ app.

