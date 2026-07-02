---
paths:
  - backend/app/models/**/*
  - backend/app/database.py
  - backend/alembic/**/*
  - data_pipeline/**/*
---
# Database Schema

## Engine

- PostgreSQL 16 with `pgvector` and `unaccent` extensions.
- Async driver: `asyncpg` via SQLAlchemy 2.0.
- Extensions auto-enabled in `backend/app/database.py` → `init_db()`.

## Tables

### Core content
- `listings` — real estate listings. Key: `product_id` (unique). Columns: title, price, area, bedrooms, bathrooms, district, city, legal_status, furniture, lat/lon, contact fields, etc. **No embedding column** (dropped in migration 20260801_0004; embeddings live in `chunks`).
- `projects` — real estate projects. Key: `id`. Columns: name, developer, location, status, amenities.
- `articles` — news/articles. Key: `id`.
- `listing_images`, `project_images`, `article_images` — associated images.

### Users & auth
- `users` — user accounts. Key: `id`. Columns: email, hashed_password, is_active, is_admin.
- `user_preferences` — per-user search/filter preferences (JSONB).

### Chat
- `chat_sessions` — chat sessions. Key: `id` (UUID). Columns: user_id (nullable), title, created_at.
- `chat_messages` — chat messages. Key: `id`. Columns: session_id, role, content, agent_used, sources_json, metadata_json (JSONB).
- `chat_feedback` — thumbs up/down feedback per message.
- `memory_proposals` — memory extraction proposals from agentic responses.

### RAG / vector store
- `chunks` — **canonical embedding store**. Polymorphic: `parent_type` ("listing" | "project" | "article") + `parent_id`. Columns:
  - `id` (Integer PK)
  - `parent_type` (String[30]), `parent_id` (Integer)
  - `chunk_type` (String[50])
  - `text` (Text)
  - `embedding` (Vector[1024]) — BAAI/bge-m3, HNSW index (m=16, ef_construction=128, cosine ops)
  - `metadata_json` (JSON, nullable)
  - `text_tsv` (tsvector, generated) — for full-text hybrid retrieval with unaccent
  - `created_at` (DateTime)
  - Indexes: `ix_chunks_parent` (parent_type, parent_id), `ix_chunks_embedding_hnsw` (HNSW), `ix_chunks_text_tsv` (GIN)

### Market
- `market_price_snapshots` — historical price aggregations with street-segment tracking.

### Pipeline tracking
- `pipeline_runs` — crawler/ingest job records (status, started_at, finished_at, stats).

### Agent observability
- `agent_traces` — top-level agent execution traces per request.
- `agent_trace_steps` — individual step details within a trace.
- `agent_retrieval_events` — retrieval events during agent execution.
- `agent_llm_calls` — LLM API calls (model, tokens, cost, latency).
- `eval_runs`, `eval_scores` — LLM-as-judge evaluation records.
- `source_readiness` — data source health/readiness checks.

## Vector Search

- Embedding dimension: **1024** (BAAI/bge-m3).
- Similarity: cosine distance operator `<=>` on `chunks.embedding`.
- Hybrid retrieval: pgvector kNN + PostgreSQL full-text (RRF fusion on `text_tsv`).
- Query pattern: `ORDER BY embedding <=> :query_embedding LIMIT :k`.

## Migrations

- Located in `backend/alembic/versions/`.
- Never edit an existing migration — always add a new file `YYYYMMDD_NNNN_description.py`.
- Check `alembic heads` after branching; multiple heads have been merged before.
