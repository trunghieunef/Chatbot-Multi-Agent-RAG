---
paths:
  - .env.example
  - docker-compose.yml
  - infra/**/*
---
# Environment & Docker

## Required Environment Variables

Set in root `.env` (never commit real values):

### Database
- `DATABASE_URL` — PostgreSQL async connection string (asyncpg)
- `REDIS_URL` — Redis connection

### Auth
- `JWT_SECRET_KEY` — JWT signing secret
- `JWT_ALGORITHM` — default HS256
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`

### LLM
- `GEMINI_API_KEY` — Google Gemini API key (router/specialists fall back to rule-based without it)
- `GEMINI_MODEL` — default `gemini-2.5-flash`
- `GEMINI_JUDGE_MODEL` — default `gemini-2.5-flash`

### Embedding
- `HF_EMBEDDING_MODEL` — default `BAAI/bge-m3`
- `EMBEDDING_DIM` — default `1024`
- `CHATBOT_EMBEDDING_LOCAL_FILES_ONLY` — default `true` (offline mode)

### Service wiring
- `AGENT_SERVICE_URL` — internal URL of agent-service (e.g. `http://agent-service:8100`)
- `AGENT_INTERNAL_KEY` — shared secret for `X-Internal-Agent-Key` header
- `NEXT_PUBLIC_API_URL` — frontend API base URL (e.g. `/api/v1`)
- `CORS_ORIGINS` — allowed CORS origins

### Agent feature flags (key ones)
- `CHATBOT_AGENT_SERVICE_ENABLED` — toggle agent-service delegation
- `AGENT_ROUTER_MODE` — `rule` | `llm` | `hybrid`
- `AGENT_AGENTIC_MODE` — `true` = agentic graph, `false` = old graph
- `AGENT_SPECIALIST_LLM_ENABLED` — LLM-powered specialists
- `AGENT_QUERY_REWRITE_ENABLED` — query rewriting
- `AGENT_MEMORY_FILTERS_ENABLED` — user preference filters

### Chat limits
- `ANON_CHAT_DAILY_LIMIT` — default 20
- `AUTH_CHAT_DAILY_LIMIT` — default 200

### Monitoring (optional)
- `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`
- `SLACK_WEBHOOK_URL` — for Alertmanager alerts

## Docker Services

| Service | Image | Port |
|---------|-------|------|
| PostgreSQL + pgvector | `pgvector/pgvector:pg16` | 5432 |
| Redis | `redis:7-alpine` | 6379 |
| Backend | Custom (FastAPI) | 8000 |
| Agent Service | Custom (FastAPI + LangGraph) | 8100 |
| Pipeline Worker | Custom (ETL) | 8200 |
| Frontend | Custom (Next.js) | 3000 |
| Prometheus | `prom/prometheus:v2.55.0` | 9090 |
| Alertmanager | `prom/alertmanager:v0.28.0` | 9093 |
| Grafana | `grafana/grafana:11.3.0` | 3001 |
| postgres-exporter | — | 9187 |
| redis-exporter | — | 9121 |
| nginx | Custom | 80, 443 |
| certbot | — | SSL certs |

## Tech Stack Versions

- Python 3.12, Next.js 16.2.3, React 19.2.4, Tailwind CSS v4
- FastAPI >=0.115.0, SQLAlchemy >=2.0.36 (asyncio + asyncpg)
- PostgreSQL 16 + pgvector, Redis 7
- LangGraph >=0.2.70, langgraph-checkpoint-sqlite >=2.0.0
- google-genai >=1.0.0, sentence-transformers >=3.0.0
- Playwright >=1.58.0 + playwright-stealth

## Monitoring Infrastructure (`infra/`)

- `infra/prometheus/` — Prometheus config + alert rules
- `infra/alertmanager/` — Alertmanager config (Slack webhook support)
- `infra/grafana/` — Grafana dashboards (health, pipeline) and provisioning
- `infra/nginx/` — nginx reverse proxy config, SSL init scripts
