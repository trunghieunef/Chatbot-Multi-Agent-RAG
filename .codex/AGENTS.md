# Real Estate Chatbot v2 — Agent Guide

> Nền tảng bất động sản tích hợp chatbot multi-agent RAG, lấy cảm hứng từ batdongsan.com.vn.

---

## Tổng quan dự án

Đây là ứng dụng full-stack bất động sản Việt Nam với 5 module chính:

1. **Crawler** — Cào dữ liệu từ batdongsan.com.vn (Playwright + Stealth)
2. **Data Pipeline** — ETL, làm sạch, enrichment, load vào DB
3. **Backend API** — FastAPI, PostgreSQL + pgvector, Redis, JWT auth
4. **Frontend** — Next.js 14 (App Router), Tailwind CSS v4, React 19
5. **RAG Chatbot** — LangGraph multi-agent, Google Gemini, ChromaDB

---

## Kiến trúc hệ thống

```
User → Frontend (Next.js :3000)
         ↓
     Backend API (FastAPI :8000)
         ↓
    ┌────┴────────────────────┐
    │                         │
PostgreSQL+pgvector      RAG Pipeline (LangGraph)
    │                    ┌────┴────┐
  Redis               Router Agent
  (cache)          ┌───┬───┬───┐
               Property Market Legal Investment
               Search   Analysis Advisor Advisor
                    │
                ChromaDB (vector store)
                    │
               Synthesizer → Response
```

### Flow xử lý Chat

```
User Query → Router Agent (Gemini classify intent)
           → Dispatch đến 1+ specialized agents
           → Agents truy vấn Vector Store + SQL
           → Synthesizer gộp kết quả
           → Final Response + Sources + Suggestions
```

---

## Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | Next.js (App Router) | 16.2.3 |
| UI Framework | React | 19.2.4 |
| Styling | Tailwind CSS | v4 |
| Icons | Lucide React | 1.8.x |
| Charts | Recharts | 3.8.x |
| Backend | FastAPI | ≥0.115.0 |
| ORM | SQLAlchemy (async) | ≥2.0.36 |
| Database | PostgreSQL + pgvector | PG 16 |
| Cache | Redis | 7 Alpine |
| Vector Store | ChromaDB | ≥0.5.0 |
| LLM | Google Gemini 2.0 Flash | — |
| Embeddings | text-embedding-004 | — |
| Agent Framework | LangGraph | ≥0.2.0 |
| Crawler | Playwright + Stealth | ≥1.58.0 |
| Auth | JWT (PyJWT + bcrypt) | — |
| Container | Docker Compose | — |

---

## Cấu trúc thư mục

```
RealEstate_Chatbot_v2/
├── backend/                        # FastAPI Backend
│   ├── main.py                     # Legacy standalone backend (đọc CSV)
│   ├── app/                        # Backend v2 (SQLAlchemy, async)
│   │   ├── main.py                 # FastAPI app + lifespan + CORS
│   │   ├── config.py               # Pydantic Settings (env vars)
│   │   ├── database.py             # SQLAlchemy async engine + session
│   │   ├── models/                 # ORM models
│   │   │   ├── listing.py          # Listing model (pgvector embedding)
│   │   │   ├── project.py          # Dự án BĐS model
│   │   │   ├── user.py             # User model (auth)
│   │   │   └── chat.py             # ChatSession + ChatMessage
│   │   ├── schemas/                # Pydantic request/response schemas
│   │   │   ├── listing.py          # ListingCreate, ListingResponse, filters
│   │   │   ├── chat.py             # ChatRequest, ChatResponse
│   │   │   ├── auth.py             # Auth schemas
│   │   │   └── common.py           # Pagination, shared schemas
│   │   ├── routers/                # API endpoints
│   │   │   ├── listings.py         # CRUD /api/v1/listings
│   │   │   ├── market.py           # /api/v1/market (stats, trends)
│   │   │   ├── auth.py             # /api/v1/auth (register, login)
│   │   │   └── chat.py             # /api/v1/chat (REST + WebSocket)
│   │   └── services/
│   │       └── chatbot/            # Chatbot service integration
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/                       # Next.js 14 Application
│   ├── app/
│   │   ├── layout.tsx              # Root layout
│   │   ├── page.tsx                # Trang chủ (hero, search, listings)
│   │   ├── globals.css             # Tailwind CSS v4 config
│   │   ├── nha-dat-ban/            # Route: nhà đất bán
│   │   ├── nha-dat-cho-thue/       # Route: nhà đất cho thuê
│   │   ├── thi-truong/             # Route: dashboard thị trường
│   │   ├── dang-nhap/              # Route: đăng nhập
│   │   └── dang-ky/                # Route: đăng ký
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Header.tsx          # Navigation header
│   │   │   └── Footer.tsx          # Site footer
│   │   ├── listing/
│   │   │   ├── ListingCard.tsx     # Card hiển thị listing
│   │   │   └── ListingGrid.tsx     # Grid + pagination
│   │   ├── search/
│   │   │   └── FilterPanel.tsx     # Bộ lọc tìm kiếm
│   │   └── chatbot/
│   │       └── ChatWidget.tsx      # Floating chat widget
│   ├── lib/
│   │   ├── api.ts                  # API client functions
│   │   ├── types.ts                # TypeScript type definitions
│   │   └── utils.ts                # Utility helpers
│   ├── package.json
│   └── tsconfig.json
│
├── RAG/                            # Multi-Agent RAG System
│   ├── config.py                   # Gemini + ChromaDB config
│   ├── state.py                    # ChatState (LangGraph shared state)
│   ├── graph.py                    # LangGraph workflow definition
│   └── agents/
│       ├── router.py               # Intent classification + routing
│       ├── property_search.py      # Tìm BĐS (placeholder)
│       ├── market_analysis.py      # Phân tích thị trường (placeholder)
│       ├── legal_advisor.py        # Tư vấn pháp lý (placeholder)
│       └── investment_advisor.py   # Tư vấn đầu tư (placeholder)
│
├── Crawl/                          # Data Crawler
│   ├── 01.crawl_listing_url.py     # Cào URLs (8 workers song song)
│   ├── 02.crawl_listing_details.py # Cào chi tiết (20+ fields)
│   ├── merge.py                    # Gộp + deduplicate CSV
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── data_pipeline/                  # ETL Pipeline
│   └── load_db.py                  # Load CSV → PostgreSQL
│
├── data/                           # Data files
│   ├── apartments.csv              # ~900KB dữ liệu thô
│   ├── apartments_cleaned.csv      # ~875KB dữ liệu đã clean
│   ├── listing_details.csv         # ~814KB chi tiết listings
│   └── listing_url.csv             # ~7.4MB URLs đã cào
│
├── batdongsancom-crawler/          # Crawler utils (clean, heatmap)
├── FrontEnd_old/                   # Legacy frontend (HTML/CSS/JS)
├── notebooks/                      # Jupyter notebooks (EDA)
│   └── 01.EDA.ipynb
│
├── docker-compose.yml              # Orchestrate all services
├── requirements.txt                # Root Python dependencies
├── .env                            # Environment variables
└── .gitignore
```

---

## Cấu hình & Environment

### Environment Variables (`.env`)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://admin:...@localhost:5432/realestate
POSTGRES_DB=realestate
POSTGRES_USER=admin
POSTGRES_PASSWORD=realestate_secret_2026

# Redis
REDIS_URL=redis://localhost:6379/0

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8001

# Google Gemini
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.0-flash

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
| ChromaDB | `chromadb/chroma:latest` | 8001 |
| Backend | Custom (FastAPI) | 8000 |
| Frontend | Custom (Next.js) | 3000 |

---

## Quy ước code

### Backend (Python)

- **Framework**: FastAPI với async/await
- **ORM**: SQLAlchemy 2.0 async mode (`asyncpg` driver)
- **Validation**: Pydantic v2 (schemas trong `backend/app/schemas/`)
- **Config**: Pydantic Settings từ `.env`
- **API versioning**: Prefix `/api/v1/`
- **Router pattern**: Mỗi resource 1 router file trong `backend/app/routers/`
- **Type hints**: Bắt buộc cho tất cả function signatures
- **Naming**: snake_case cho Python, PascalCase cho classes
- **Docstrings**: Viết cho tất cả modules, classes, và functions quan trọng

### Frontend (TypeScript/React)

- **Framework**: Next.js 14+ App Router (`app/` directory)
- **Styling**: Tailwind CSS v4 (PostCSS plugin, không phải v3 config)
- **Language**: TypeScript strict
- **Components**: Functional components + React hooks
- **Naming**: PascalCase cho components, camelCase cho functions/variables
- **File convention**: Component files dùng `.tsx`, utilities dùng `.ts`
- **Icons**: Dùng `lucide-react`
- **Charts**: Dùng `recharts`
- **API calls**: Qua `lib/api.ts` (centralized API client)
- **Types**: Defined trong `lib/types.ts`

### RAG System (Python)

- **Framework**: LangGraph (StateGraph)
- **LLM**: Google Gemini via `google-generativeai` SDK
- **State**: `ChatState` (extends `MessagesState` từ LangGraph)
- **Pattern**: Router Agent → Specialized Agents → Synthesizer → Response
- **Fallback**: Keyword-based routing khi Gemini unavailable
- **Config**: Trong `RAG/config.py`

### Crawler (Python)

- **Tool**: Playwright + playwright-stealth
- **Parallel**: 8 workers cho URL crawling
- **Output**: CSV files trong `data/`
- **Anti-detection**: Stealth mode, random delays, user-agent rotation

---

## Database Schema

### Bảng chính

| Table | Mô tả | Key columns |
|-------|--------|-------------|
| `listings` | Tin đăng BĐS | product_id, title, price, area, bedrooms, location, embedding (vector) |
| `projects` | Dự án BĐS | name, developer, location, status, amenities, embedding (vector) |
| `users` | Tài khoản người dùng | email, hashed_password |
| `chat_sessions` | Phiên chat | user_id, created_at |
| `chat_messages` | Tin nhắn chat | session_id, role, content, agent_used, metadata (JSONB) |

### Vector Search

- Extension: `pgvector`
- Embedding dimension: `1536` (text-embedding-004)
- Similarity: Cosine similarity trên cột `embedding`

---

## Multi-Agent RAG Architecture

### Agents

| Agent | Trigger Keywords | Chức năng |
|-------|-----------------|-----------|
| **Router** | (all queries) | Classify intent, extract filters, route to agents |
| **Property Search** | tìm, mua, thuê, căn hộ, nhà, đất | Vector + SQL search, gợi ý BĐS |
| **Market Analysis** | giá, thị trường, xu hướng, thống kê | Trends, so sánh giá, cung-cầu |
| **Legal Advisor** | pháp lý, luật, thủ tục, công chứng, thuế | Tư vấn luật BĐS, thủ tục mua bán |
| **Investment Advisor** | đầu tư, ROI, lợi nhuận, sinh lời | ROI calculator, so sánh kênh đầu tư |

### LangGraph Workflow

```
START → router → [conditional routing] → agent(s) → synthesizer → END
```

### State Schema (`ChatState`)

```python
class ChatState(MessagesState):
    user_query: str              # Original user query
    intent: str                  # Classified intent
    target_agents: list[str]     # Agents to dispatch to
    search_filters: dict         # Extracted search filters
    retrieved_listings: list     # Found listings
    retrieved_docs: list         # Knowledge docs
    agent_results: dict          # Results from each agent
    final_response: str          # Synthesized answer
    sources: list[dict]          # Citations
    suggested_actions: list[str] # Follow-up suggestions
    agent_used: str              # Which agents contributed
```

---

## API Endpoints

### Listings
```
GET  /api/v1/listings              # List + filter + pagination
GET  /api/v1/listings/{id}         # Detail
GET  /api/v1/listings/search       # Full-text search
GET  /api/v1/listings/similar/{id} # Similar listings (vector)
```

### Market
```
GET  /api/v1/market/stats          # Thống kê tổng quan
GET  /api/v1/market/price-trends   # Xu hướng giá
GET  /api/v1/market/heatmap        # Dữ liệu heatmap
```

### Chat
```
POST /api/v1/chat                  # Send message (REST)
WS   /api/v1/chat/ws               # WebSocket real-time
GET  /api/v1/chat/sessions         # Chat history
GET  /api/v1/chat/sessions/{id}    # Session detail
```

### Auth
```
POST /api/v1/auth/register         # Đăng ký
POST /api/v1/auth/login            # Đăng nhập (JWT)
```

### System
```
GET  /api/v1/health                # Health check
```

---

## Trạng thái hiện tại

### Đã hoàn thành
- Crawler URLs + Details (Playwright stealth, 8 workers)
- Merge & deduplicate tool
- Backend v2 scaffolding (FastAPI + SQLAlchemy async + pgvector)
- Database schema (models, migrations setup)
- API routers: listings, market, auth, chat
- Frontend: Next.js 14 setup, trang chủ, routing cơ bản
- Frontend components: Header, Footer, ListingCard, ListingGrid, FilterPanel, ChatWidget
- RAG: LangGraph graph, state schema, 5 agents (structure)
- Docker Compose (PostgreSQL, Redis, ChromaDB, Backend, Frontend)
- Data pipeline: load_db.py

### Đang phát triển / Placeholder
- RAG agents (property_search, market_analysis, legal_advisor, investment_advisor) — có structure nhưng logic là placeholder
- ChromaDB integration (chưa tạo embeddings)
- Frontend pages chi tiết (listing detail, dự án)
- WebSocket chat

### Chưa triển khai
- Embedding generation pipeline
- Knowledge base pháp lý (Luật Nhà ở, Luật Đất đai)
- Crawler cho nhà đất cho thuê + dự án + tin tức
- Scheduled crawling (APScheduler)
- Map integration (Leaflet/MapboxGL)


- CI/CD pipeline
- Production deployment

---

## Hướng dẫn phát triển

### Khởi chạy services (Docker)
```bash
docker-compose up -d postgres redis chromadb
```

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev    # http://localhost:3000
```

### Chạy toàn bộ
```bash
docker-compose up --build
```

---

## Lưu ý quan trọng

1. **Hai backend**: Có 2 file `main.py` — `backend/main.py` (legacy, đọc CSV) và `backend/app/main.py` (v2, SQLAlchemy async). **Sử dụng `backend/app/main.py`** cho development mới.

2. **Tailwind CSS v4**: Frontend dùng Tailwind v4 với PostCSS plugin (`@tailwindcss/postcss`), KHÔNG phải v3 config-based. Không có file `tailwind.config.ts` chuyên dụng.

3. **pgvector**: Database cần extension `vector`. Được tự động enable trong `database.py` → `init_db()`.

4. **Gemini API Key**: Cần set `GEMINI_API_KEY` trong `.env` để RAG router hoạt động. Không có key sẽ fallback về keyword routing.

5. **Data files**: CSV files trong `data/` không được tracked bởi git (trừ `apartments.csv` và `listing_url.csv`). Cần chạy crawler để lấy dữ liệu mới.

6. **Legacy code**: `FrontEnd_old/` chứa frontend HTML/CSS/JS cũ, `backend/main.py` (root) là backend cũ. Cả hai giữ lại để tham khảo, KHÔNG sử dụng cho development mới.

7. **Ngôn ngữ**: Dự án phục vụ thị trường Việt Nam. UI, prompts, và responses đều bằng tiếng Việt. Code comments/docstrings bằng tiếng Anh.

---

## Session Update - MVP RAG Hugging Face Dataset

### Tasks da hoan thanh trong phien nay

- Da trien khai RAG MVP don gian cho dataset Hugging Face `tinixai/vietnam-real-estates`.
- Da them service RAG moi trong `backend/app/services/rag/`.
- Da thay placeholder cua `POST /api/v1/chat` bang pipeline `run_simple_rag`.
- Da them script ingest du lieu Hugging Face: `backend/scripts/load_hf_real_estates.py`.
- Da map du lieu Hugging Face sang bang `listings`, gom title, description, property type, location, price, area, bedrooms, bathrooms, post date.
- Da tao embedding bang Gemini va luu vao cot `Listing.embedding`.
- Da cap nhat embedding model sang `gemini-embedding-2`.
- Da ep embedding output ve `768` dimensions de khop `Vector(768)` trong model SQLAlchemy.
- Da cap nhat `backend/requirements.txt` va root `requirements.txt` voi `google-genai`, `datasets`, `pyarrow`.
- Da cap nhat frontend `ChatWidget` de hien thi `sources` tu RAG response.
- Da them type `ChatSource` trong `frontend/lib/types.ts`.
- Da them unit tests cho mapping du lieu, build document, filter extraction, source formatting, Gemini client lifetime, va fallback answer.
- Da sua loi Gemini client bi dong som khi goi SDK.
- Da them fallback answer khi Gemini `generate_content` loi quota/API, de endpoint van tra ket qua tu retrieved listings.
- Da cai dependency vao `.venv`.
- Da rebuild/recreate backend Docker container de nhan requirements moi va `.env` hien tai.
- Da ingest smoke test 20 dong tu Hugging Face vao PostgreSQL.
- Da xac nhan DB co `20` dong `hf-*` va ca `20` dong deu co embedding.
- Da test `POST /api/v1/chat` thanh cong, tra `200`, `agent_used = simple_rag`, va co `3` sources.

### Trang thai hien tai

- Backend dang chay qua Docker o `http://localhost:8000`.
- Health check backend pass: `GET /api/v1/health -> 200`.
- PostgreSQL + pgvector dang chay va healthy.
- Redis va ChromaDB dang chay, nhung RAG MVP hien khong dung ChromaDB.
- DB hien co 20 listing tu Hugging Face de smoke test.
- Chat API hoat dong voi fallback answer neu Gemini generate bi quota.
- Gemini embedding hoat dong voi `gemini-embedding-2`.
- Gemini generate hien bi quota `429 RESOURCE_EXHAUSTED` voi model `gemini-2.0-flash`, nen cau tra loi tu nhien bang LLM chua chay on dinh.
- API van usable vi fallback answer dung top retrieved listings va sources.
- Frontend code da duoc cap nhat de hien thi sources, nhung frontend dev server nen chay thu cong bang:
  ```powershell
  cd D:\CODE\RealEstate_Chatbot_v2\frontend
  npm.cmd run dev
  ```
- Targeted lint cho file frontend da sua tung pass truoc do.
- Full frontend lint van co loi cu ngoai pham vi RAG o cac page/component khac.
- Docker frontend chua chay duoc vi `frontend/Dockerfile` khong ton tai.

### Quyet dinh quan trong da dua ra

- MVP dung PostgreSQL + pgvector lam vector store chinh, khong dung ChromaDB cho ban don gian.
- Khong dung scaffold LangGraph multi-agent cu cho MVP nay vi phan do dang placeholder va lech namespace.
- RAG MVP di theo pipeline don gian: extract filters -> embed query -> pgvector search -> Gemini generate hoac fallback answer.
- Dataset ingest mac dinh huong toi 50k dong, nhung smoke test chi dung 20 dong truoc.
- Embedding model dung `gemini-embedding-2`, cau hinh `output_dimensionality = 768`.
- Giu `Listing.embedding = Vector(768)` thay vi doi schema DB.
- Neu Gemini generate loi quota/API, khong lam endpoint fail; tra fallback answer tu retrieved listings.
- `sources` trong chat response dung metadata noi bo tu DB, vi dataset Hugging Face khong co URL listing goc on dinh.
- Development moi tiep tuc dung `backend/app/main.py`, khong dung `backend/main.py` legacy.

### Verification da chay

```powershell
.venv\Scripts\python.exe -m compileall backend\app backend\scripts backend\tests
.venv\Scripts\python.exe -m pytest backend\tests\test_simple_rag.py -q
```

Ket qua test backend moi nhat:

```text
6 passed, 1 warning
```

Smoke test API:

```text
POST http://127.0.0.1:8000/api/v1/chat
status: 200
agent_used: simple_rag
sources: 3
```

DB check:

```sql
select count(*) as hf_total, count(embedding) as hf_embedded
from listings
where product_id like 'hf-%';
```

Ket qua:

```text
hf_total = 20
hf_embedded = 20
```

### Buoc tiep theo cho phien sau

1. Chay frontend thu cong bang `npm.cmd run dev` va test chat widget tren `http://localhost:3000`.
2. Neu widget goi API sai base URL, kiem tra `NEXT_PUBLIC_API_URL` va proxy frontend.
3. Fix hoac doi Gemini generate quota/model/key de cau tra loi LLM chay thay vi fallback.
4. Tang ingest theo tung muc:
   ```powershell
   .venv\Scripts\python.exe backend\scripts\load_hf_real_estates.py --limit 1000 --batch-size 100
   ```
   Sau khi on moi tang len `--limit 50000`.
5. Giam noise log SQLAlchemy neu can bang cach set `DEBUG=False` trong `.env`.
6. Fix cac loi lint frontend cu ngoai pham vi RAG neu muon `npm run lint` pass toan bo.
7. Sau khi ingest lon hon, test nhieu cau hoi:
   - `Tim can ho 2 phong ngu o Ha Noi duoi 5 ty`
   - `Tim nha o TP Ho Chi Minh duoi 8 ty`
   - `Tim dat o Ha Noi dien tich tren 100m2`
   - `Tim can ho o Tay Ho duoi 8 ty`
