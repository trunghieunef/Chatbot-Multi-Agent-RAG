# Project Structure

Full-stack Vietnamese real estate chatbot platform with 5 modules.

## Module Map

- `backend/app/` — FastAPI v2 backend (SQLAlchemy async, pgvector). Use this for all new development.
- `backend/main.py` — Legacy CSV-based backend. Do NOT use for new work.
- `backend/app/models/` — ORM models (Listing, Project, User, Chat).
- `backend/app/schemas/` — Pydantic request/response contracts.
- `backend/app/routers/` — API endpoint handlers. One file per resource.
- `backend/app/services/` — Business logic and external integrations.
- `frontend/app/` — Next.js 14 App Router pages.
- `frontend/components/` — Reusable UI components (layout, listing, search, chatbot).
- `frontend/lib/` — API client (`api.ts`), types (`types.ts`), utilities (`utils.ts`).
- `RAG/` — LangGraph multi-agent chatbot. Graph, state, and agent definitions.
- `RAG/agents/` — Specialized agents (router, property_search, market_analysis, legal_advisor, investment_advisor).
- `Crawl/` — Playwright crawler scripts with stealth and parallel workers.
- `data_pipeline/` — ETL: CSV cleaning, enrichment, PostgreSQL loading.
- `data/` — Local CSV/database assets. Not fully tracked by git.
- `batdongsancom-crawler/` — Crawler utilities (clean, heatmap).
- `FrontEnd_old/` — Legacy HTML/CSS/JS frontend. Reference only, do NOT use.

## Two Backends Warning

There are 2 `main.py` files:
- `backend/main.py` — legacy, reads CSV directly. DO NOT USE.
- `backend/app/main.py` — v2, SQLAlchemy async + pgvector. USE THIS.
