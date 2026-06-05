# Crawl, Publish, And Index Pipeline

## Context

The project ingests real-estate data from crawlers and local knowledge sources into PostgreSQL. Public web/API visibility depends on structured parent tables. Chatbot retrieval depends on semantic chunks indexed for the internal Agent Service.

The root-level `chatbot/` package is legacy scaffold code. Active production chat and retrieval orchestration now runs through the backend plus the internal `agent_service`.

## Architecture Decisions

| Area | Decision |
|---|---|
| Parent storage | PostgreSQL parent tables are the source of truth for public API visibility. |
| Vector storage | PostgreSQL + pgvector stores `chunks.embedding`. |
| Embedding model | BGE-M3 `BAAI/bge-m3`, 1024 dimensions. |
| Retrieval owner | Internal Agent Service tools. |
| Frontend chat entrypoint | Backend `/api/v1/chat` only. |
| Agent orchestration | `agent_service` owns LangGraph, Gemini, trace, eval, and memory proposals. |

**Current HEAD note:** The active retrieval path is PostgreSQL + pgvector, not ChromaDB/Qdrant. Current HEAD uses BGE-M3 dense embeddings with 1024 dimensions. Migration `20260801_0007_bge_m3_embeddings.py` clears existing `chunks`, changes `chunks.embedding` to `vector(1024)`, and requires re-ingesting indexed sources.

**Crawler status note:** `crawler/projects/` and `crawler/news/` now have fixture-backed parser selectors. Live smoke runs should still start small because batdongsan.com.vn DOM and anti-bot behavior can change.

**Publish-first listing ingestion note:** Current listing ingestion is intentionally publish-first: crawled detail CSV rows are upserted into `listings` before semantic chunks are embedded. The web UI only depends on `listings`; chatbot retrieval depends on `chunks`, so embedding failures must not prevent crawled listings from appearing on the site.

**Unified source flow note:** Current source ingestion is intentionally publish-first: crawled CSV rows are published as structured parent rows before semantic chunks are embedded. Chatbot retrieval reads indexed `chunks` through the internal Agent Service tools. Web/API visibility still depends on parent tables (`listings`, `projects`, `articles`) and must not be blocked by embedding/index failures. Agent readiness surfaces missing parent/chunk data in admin views and chat trace warnings.

| Source | CSV or source artifact | Parent table for web/API | Chunk parent_type for chatbot |
|---|---|---|---|
| Sale/rent listings | `data/raw/*_details.csv` | `listings` | `listing` |
| Projects | `data/raw/projects_details.csv` | `projects` | `project` |
| News | `data/raw/news_articles.csv` | `articles` | `article` |
| Legal KB | `data/knowledge/raw/*` | `articles` | `article` |

## Source Flow

```text
Crawler or knowledge source
  |
  v
Clean and normalize
  |
  v
Publish parent records to PostgreSQL
  |
  |-- listings
  |-- projects
  |-- articles
  |
  v
Build semantic chunks
  |
  v
Embed with BGE-M3
  |
  v
Store chunks.embedding vector(1024)
  |
  v
Internal Agent Service retrieval tools
```

Publishing parent rows and indexing chunks are separate reliability domains. Parent records should be visible to public APIs even when embedding providers, vector indexing, or chunk generation are temporarily unavailable.

## Retrieval Ownership

Active chatbot retrieval belongs to `agent_service/tools/`, not the root-level `chatbot/` scaffold. Agent Service tools read indexed `chunks`, resolve them back to parent records, and return source metadata and trace warnings to the graph.

Expected retrieval behavior:

- Use structured filters against parent tables when the user request contains price, location, type, or status constraints.
- Search semantic `chunks` for the relevant parent types.
- Resolve chunk hits back to `listings`, `projects`, or `articles`.
- Surface missing or stale parent/chunk data in readiness checks and trace warnings.
- Keep public web/API responses independent from chunk indexing health.

## Database Shape

Parent tables:

- `listings`
- `projects`
- `articles`

Retrieval table:

- `chunks`

Important `chunks` fields:

- `parent_type`: `listing`, `project`, or `article`.
- `parent_id`: application-level reference to the parent row.
- `chunk_type`: semantic section such as overview, description, location, amenities, legal section, or article body.
- `text`: text used for retrieval and synthesis context.
- `embedding`: BGE-M3 vector with 1024 dimensions.

## Operational Readiness

Agent readiness checks should make data availability visible without blocking user-facing parent data:

- Parent table row counts.
- Chunk counts by `parent_type`.
- Missing chunks for indexed parent types.
- Embedding dimension/config mismatches.
- Recent ingestion or indexing failures.
- Trace warnings emitted during chat turns.

## Legacy Scaffold

The root-level `chatbot/` package remains in the repository as legacy scaffold code. Do not delete it as part of pipeline documentation cleanup. New documentation should refer to `agent_service` for active LangGraph/RAG/Gemini orchestration and to the backend for public API contracts.

## Verification

Relevant verification commands:

```powershell
pytest backend\tests -q
python -m compileall backend\app agent_service data_pipeline chatbot crawler
docker compose config
```
