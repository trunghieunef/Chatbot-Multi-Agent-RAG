---
# Development Commands

## Infrastructure
```bash
docker-compose up -d postgres redis       # start local DB + cache
docker-compose up --build                 # full stack (all services + monitoring)
```

## Backend (public API, :8000)
```bash
pip install -r services/backend/requirements.txt
cd services/backend && alembic upgrade head        # apply DB migrations
cd services/backend && alembic heads               # check for multiple heads after branching
uvicorn services.backend.app.main:app --reload --port 8000
```

All commands run from the **repo root** unless they `cd` (imports start at the root).

## Agent Service (:8100)
```bash
pip install -r requirements.txt           # or services/agent_service/requirements.txt
uvicorn services.agent_service.main:app --reload --port 8100
```

## Pipeline Worker (:8200)
```bash
uvicorn services.pipeline_worker.main:app --reload --port 8200
```

## Frontend (:3000)
```bash
cd services/frontend && npm install
cd services/frontend && npm run dev
cd services/frontend && npm run lint               # ESLint — run for any frontend change
cd services/frontend && npm run build              # production build
```

## Data Pipeline
```bash
# Crawl
python -m etl.crawler.sale.crawl_urls --pages 1 5 --output data/raw/listing_urls.csv
python -m etl.crawler.sale.crawl_details --input data/raw/listing_urls.csv --output data/raw/listing_details.csv

# Ingest
python -m etl.data_pipeline.ingestors.listings_ingestor --csv data/raw/listing_details.csv --batch-size 50
python -m etl.data_pipeline.ingestors.news_ingestor --csv data/raw/news_details.csv
```

## Tests & Verification

Two pytest suites, both configured by the root `pytest.ini` (`pythonpath = .`):

```bash
# Backend tests
python -m pytest services/backend/tests -q

# Agent service tests (run from repo root)
python -m pytest services/agent_service/tests -q
python -m pytest services/agent_service/tests/test_router_modes.py -q        # single file
python -m pytest services/agent_service/tests/test_synthesis.py::test_name -q # single test

# Python syntax/import check
python -m compileall shared services/backend/app services/agent_service services/pipeline_worker etl
```

Agent tests use a fake LLM transport and do not hit real Gemini — follow this pattern for new tests.
