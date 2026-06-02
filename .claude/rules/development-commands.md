# Development Commands

## Infrastructure
- `docker-compose up -d postgres redis chromadb` — start local DB, cache, vector store

## Backend
- `cd backend && pip install -r requirements.txt` — install dependencies
- `cd backend && uvicorn app.main:app --reload --port 8000` — run FastAPI dev server

## Frontend
- `cd frontend && npm install` — install dependencies
- `cd frontend && npm run dev` — run Next.js at http://localhost:3000
- `cd frontend && npm run lint` — run ESLint
- `cd frontend && npm run build` — production build

## Verification
- `python -m compileall backend\app RAG data_pipeline` — Python syntax/import check
- `python -m data_pipeline.load_db` — load CSV data into PostgreSQL

## Full Stack
- `docker-compose up --build` — build and run everything
