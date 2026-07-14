---
# Development Commands

## Infrastructure
```bash
docker-compose up -d postgres redis       # start local DB + cache
docker-compose up --build                 # full stack (all services + monitoring)
```

## Backend (public API, :8000)
```bash
cd backend && pip install -r requirements.txt
cd backend && alembic upgrade head        # apply DB migrations
cd backend && alembic heads               # check for multiple heads after branching
cd backend && uvicorn app.main:app --reload --port 8000
```

## Agent Service (:8100)
Run from **repo root** so `agent_service.*` imports resolve:
```bash
pip install -r requirements.txt           # or agent_service/requirements.txt
uvicorn agent_service.main:app --reload --port 8100
```

## Pipeline Worker (:8200)
```bash
uvicorn pipeline_worker.main:app --reload --port 8200
```

## Frontend (:3000)
```bash
cd frontend && npm install
cd frontend && npm run dev
cd frontend && npm run lint               # ESLint — run for any frontend change
cd frontend && npm run build              # production build
```

## Data Pipeline
```bash
# Crawl
python -m crawler.sale.crawl_urls --pages 1 5 --output data/raw/listing_urls.csv
python -m crawler.sale.crawl_details --input data/raw/listing_urls.csv --output data/raw/listing_details.csv

# Ingest
python -m data_pipeline.ingestors.listings_ingestor --csv data/raw/listing_details.csv --batch-size 50
python -m data_pipeline.ingestors.news_ingestor --csv data/raw/news_details.csv
```

## Tests & Verification

Two separate pytest suites — each has its own `conftest.py` that fixes `sys.path`:

```bash
# Backend tests
cd backend && python -m pytest tests -q

# Agent service tests (run from repo root)
python -m pytest agent_service/tests -q
python -m pytest agent_service/tests/test_router_modes.py -q        # single file
python -m pytest agent_service/tests/test_synthesis.py::test_name -q # single test

# Python syntax/import check
python -m compileall backend/app agent_service pipeline_worker data_pipeline crawler
```

Agent tests use a fake LLM transport and do not hit real Gemini — follow this pattern for new tests.
