# Environment & Docker

## Required Environment Variables

Set in `.env` (never commit real values):
- `DATABASE_URL` — PostgreSQL async connection string
- `REDIS_URL` — Redis connection
- `GEMINI_API_KEY` — Google Gemini API key (RAG router needs this; falls back to keyword routing without it)
- `NEXT_PUBLIC_API_URL` — Frontend API base URL
- `JWT_SECRET_KEY` — JWT signing secret
- `CORS_ORIGINS` — Allowed CORS origins

## Docker Services

| Service | Image | Port |
|---------|-------|------|
| PostgreSQL + pgvector | `pgvector/pgvector:pg16` | 5432 |
| Redis | `redis:7-alpine` | 6379 |
| Pipeline Worker | Custom (ETL) | — |
| Backend | Custom (FastAPI) | 8000 |
| Frontend | Custom (Next.js) | 3000 |

## Tech Stack Versions

- Next.js 16.2.3, React 19.2.4, Tailwind CSS v4
- FastAPI >=0.115.0, SQLAlchemy >=2.0.36
- PostgreSQL 16 + pgvector, Redis 7
- LangGraph >=0.2.0, Playwright >=1.58.0
- Google Gemini 2.5 Flash, BAAI/bge-m3 embedding
