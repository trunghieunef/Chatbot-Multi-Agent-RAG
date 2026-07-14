---
# Security

- Keep all secrets in root `.env`. Never commit real API keys, passwords, or JWT secrets.
- Critical env vars: `GEMINI_API_KEY`, `AGENT_INTERNAL_KEY`, `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `NEXT_PUBLIC_API_URL`.
- `AGENT_INTERNAL_KEY` is the shared secret for `X-Internal-Agent-Key` — required for backend ↔ agent-service communication.
- CSV data files in `data/` are not fully tracked by git.
- ORM (SQLAlchemy) prevents SQL injection. Do not use raw SQL with user-supplied input.
- Next.js auto-escapes output to prevent XSS.
- CORS: configured in `backend/app/main.py` via `CORS_ORIGINS` env var.
- Without `GEMINI_API_KEY` the router falls back to rule-based routing and specialists to keyword mode; embeddings still work (bge-m3 is local).
