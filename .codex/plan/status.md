# Project Status — Master Index

> Read this file first. It describes the current repo state, the phase order, and how to use each phase file.

---

## How To Use This Plan

Each phase file is a **self-contained instruction set**. An agent should:

1. Read this `status.md` to understand current state and pick the next incomplete phase.
2. Open the target phase file.
3. Execute tasks **in order** within that phase (tasks have dependency notes).
4. Run the verification commands listed at the end of each phase.
5. Update the task checkboxes (`- [x]`) after completing each item.

**Rules for agents:**

- Do NOT skip prerequisite phases.
- Do NOT implement features marked "Out Of Scope" in a phase file.
- When a task says "verify", run the command and confirm the output before marking done.
- When a task gives a file path, use it exactly — paths are relative to the repo root `d:\CODE\RealEstate_Chatbot_v2\`.
- All backend code uses async/await. All new Python code must have type hints.
- Frontend uses Next.js App Router, TypeScript, Tailwind CSS v4, and `lucide-react` icons.

---

## Current Repo State

### Working

- `Crawl/01.crawl_listing_url.py` — crawl sale listing URLs (8 workers, stealth, dedup)
- `Crawl/02.crawl_listing_details.py` — crawl detail pages (4 workers, resume, 20+ fields, `--limit` flag)
- `Crawl/merge.py` — merge worker tmp files, dedup by product_id, `--keep-tmp` flag
- `backend/app/` — FastAPI v2 with async SQLAlchemy, 4 routers (listings, market, auth, chat), models, schemas
- `frontend/` — Next.js 14 with homepage, listing pages, auth pages, market page, chat widget
- `RAG/` — LangGraph graph, state schema, 5 agent stubs (router, property_search, market_analysis, legal_advisor, investment_advisor)
- `data_pipeline/load_db.py` — CSV → PostgreSQL loader (insert-only, no upsert)
- `docker-compose.yml` — postgres, redis, chromadb, backend, frontend

### Known Bugs To Fix

- **Route collision**: `backend/app/routers/listings.py` declares `/{listing_id}` before `/by-product-id/` and `/similar/`, causing FastAPI to misroute.
- **RAG folder case**: Folder is `RAG/` (uppercase) but imports use `from rag.*` (lowercase). Works on Windows, fails on Linux/Docker.
- **Crawler merge bug**: `01.crawl_listing_url.py` `_merge_tmp_files` sorts by `page_num` but that field is commented out in `FIELDS`.
- **Data location**: Files are in `data/` flat, but pipeline expects `data/raw/` structure.

### Not Implemented

- Alembic migrations (using `create_all` directly)
- Embedding generation pipeline
- RAG agents with real logic (all are placeholders)
- Knowledge base (legal docs)
- Upsert in data loader (only inserts new rows)
- Crawler for rent/projects/news
- Scheduled crawling
- Redis caching
- WebSocket chat streaming
- Map integration
- Tests / CI / CD

### Data Files

| File | Size | Description |
|------|------|-------------|
| `data/listing_url.csv` | ~7.4 MB | Crawled sale listing URLs |
| `data/listing_details.csv` | ~814 KB | Crawled listing detail fields |
| `data/apartments.csv` | ~900 KB | Legacy apartment data |
| `data/apartments_cleaned.csv` | ~875 KB | Legacy cleaned data |
| `data/apartments.db` | ~459 KB | Legacy SQLite database |

### Stale / Legacy (do not use for new development)

- `backend/main.py` — legacy CSV-based backend
- `batdongsancom-crawler/` — legacy crawler utils (clean.py, heatmap)
- `FrontEnd_old/` — legacy HTML/CSS/JS frontend (if present)

---

## Phase Order

```
Phase 0   Data Directory + Database Foundation    Week 1-2
Phase 1   Backend API Stabilization               Week 2-3
Phase 2   Frontend MVP                            Week 3-4
Phase 3   RAG Chatbot MVP                         Week 4-6
Phase 4   Testing, CI, Production Ready           Week 6-8
Phase 5   Post-MVP Backlog                        After MVP
```

**Critical path:** Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4

Phase 5 items must NOT be implemented before Phase 4 is complete.

---

## MVP Acceptance Criteria

All of these must pass before MVP is considered done:

- [ ] `docker-compose up -d postgres` starts PostgreSQL with pgvector.
- [ ] `cd backend; alembic upgrade head` creates the schema.
- [ ] `python -m data_pipeline.run_pipeline --skip-crawl --input data\raw\listing_details.csv` loads data.
- [ ] `cd backend; uvicorn app.main:app --port 8000` starts without errors.
- [ ] `GET /api/v1/listings?city=Ho Chi Minh` returns real listings.
- [ ] `POST /api/v1/chat` returns RAG-backed response (not placeholder).
- [ ] `cd frontend; npm run build` succeeds.
- [ ] Frontend shows real listings, filters, detail pages, auth, market stats, and chat.
- [ ] `python -m compileall backend\app RAG data_pipeline` passes.
- [ ] `pytest backend/tests -v` passes.

---

## Environment Variables (MVP Required)

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GEMINI_API_KEY` | Yes | Google Gemini API for RAG |
| `JWT_SECRET_KEY` | Yes | JWT token signing |
| `NEXT_PUBLIC_API_URL` | Yes | Frontend → Backend URL |
| `REDIS_URL` | No (post-MVP) | Redis cache connection |
| `CHROMA_HOST` | No (post-MVP) | ChromaDB host |
