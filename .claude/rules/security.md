# Security

- Keep all secrets in `.env`. Never commit real API keys, passwords, or JWT secrets.
- Required env vars: `GEMINI_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `NEXT_PUBLIC_API_URL`, `JWT_SECRET_KEY`.
- CSV data files in `data/` are not fully tracked by git (except `apartments.csv` and `listing_url.csv`).
- ORM (SQLAlchemy) prevents SQL injection. Do not use raw SQL with user input.
- Next.js auto-escapes output to prevent XSS.
- CORS: configured in `backend/app/main.py` via `CORS_ORIGINS` env var.
