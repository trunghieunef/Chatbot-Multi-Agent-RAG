---
paths:
  - backend/app/models/**/*
  - backend/app/database.py
  - data_pipeline/**/*
---
# Database Schema

## Engine

- PostgreSQL 16 with `pgvector` extension.
- Async driver: `asyncpg` via SQLAlchemy 2.0.
- Extension `vector` auto-enabled in `database.py` -> `init_db()`.

## Tables

- `listings` — real estate listings. Key: product_id (unique). Columns: title, price, area, bedrooms, bathrooms, district, city, embedding (vector 1536).
- `projects` — real estate projects. Key: id. Columns: name, developer, location, status, amenities, embedding (vector 1536).
- `users` — user accounts. Key: id. Columns: email, hashed_password.
- `chat_sessions` — chat sessions. Key: id (UUID). Columns: user_id, title.
- `chat_messages` — chat messages. Key: id. Columns: session_id, role, content, agent_used, metadata_json (JSONB).

## Vector Search

- Embedding dimension: 1536 (text-embedding-004).
- Similarity: cosine distance on `embedding` column.
- Query pattern: `ORDER BY embedding <=> query_embedding LIMIT K`.
