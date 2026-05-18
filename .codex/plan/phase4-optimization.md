# Phase 4 — Testing, CI, and Production Readiness

> **Prerequisite:** Phase 3 complete. RAG chatbot returns real responses.
> **Goal:** Make the MVP verifiable, buildable, and deployable.
> **Timeline:** Week 6-8

---

## Section 1: Backend Unit Tests

**Directory:** `backend/tests/`

### Tasks

- [ ] Create `backend/tests/test_parsers.py`:
  - Test `parse_price_billion("4,68 tỷ")` → `4.68`
  - Test `parse_price_billion("500 triệu")` → `0.5`
  - Test `parse_price_billion("Thỏa thuận")` → `None`
  - Test `parse_area("80 m²")` → `80.0`
  - Test `parse_int_safe("3 phòng")` → `3`
  - Test `parse_int_safe("")` → `None`
- [ ] Create `backend/tests/test_loader.py`:
  - Test upsert: insert a row, then insert same `product_id` with changed price → verify price is updated.
  - Test dedup: insert same `product_id` twice → only 1 row in DB.
- [ ] Create `backend/tests/test_listings.py`:
  - Test `GET /api/v1/listings` returns 200 with paginated response.
  - Test `GET /api/v1/listings?min_price=1&max_price=3` filters correctly.
  - Test `GET /api/v1/listings/999999` returns 404.
  - Test `GET /api/v1/listings/similar/1` returns list.
- [ ] Create `backend/tests/test_market.py`:
  - Test `GET /api/v1/market/stats` returns 200 with numeric values.
- [ ] Create `backend/tests/test_auth.py`:
  - Test register → login → get token.
  - Test login with wrong password → 401.
- [ ] Create `backend/tests/test_chat.py`:
  - Test `POST /api/v1/chat` returns response (even if RAG fails, should return fallback).

### Verify

```powershell
cd backend
pytest tests -v
# All tests pass
```

---

## Section 2: RAG Tests

**Directory:** `backend/tests/` or `rag/tests/`

### Tasks

- [ ] Create `test_rag_router.py`:
  - Test intent classification with fixed queries (mock Gemini response):
    - `"Tìm căn hộ Quận 7"` → intent includes `property_search`
    - `"Giá nhà hiện nay"` → intent includes `market_analysis`
    - `"Thủ tục mua nhà"` → intent includes `legal_advisor`
- [ ] Create `test_rag_search.py`:
  - Seed a test listing in DB, test that property search agent finds it.
- [ ] Create `test_rag_fallback.py`:
  - Test that when Gemini API key is missing, agents return fallback responses (not crash).
- [ ] All RAG tests should pass **without** live Gemini API calls by default (use mocks).
- [ ] Add optional live test mode via env var `RAG_TEST_LIVE=1`.

### Verify

```powershell
pytest backend/tests/test_rag_*.py -v
# All pass without GEMINI_API_KEY set (using mocks)
```

---

## Section 3: Frontend Build Checks

### Tasks

- [ ] Run `cd frontend; npm run lint` — fix all errors.
- [ ] Run `cd frontend; npm run build` — fix all build errors.
- [ ] Fix any TypeScript type errors in API response types (ensure types match actual backend responses).
- [ ] Manually verify pages at mobile (375px) and desktop (1440px) widths.

### Verify

```powershell
cd frontend
npm run lint
# 0 errors, 0 warnings
npm run build
# Build succeeds
```

---

## Section 4: GitHub Actions CI

**File:** `.github/workflows/ci.yml`

### Tasks

- [ ] Create CI workflow with two jobs:

**Job 1: Backend**
```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install -r backend/requirements.txt
- run: python -m compileall backend/app rag data_pipeline
- run: cd backend && pytest tests -v
```

**Job 2: Frontend**
```yaml
- uses: actions/setup-node@v4
  with: { node-version: "20" }
- run: cd frontend && npm ci
- run: cd frontend && npm run lint
- run: cd frontend && npm run build
```

- [ ] Trigger on: `push` to `main`, `pull_request` to `main`.
- [ ] Do NOT add Docker build job yet (too slow for MVP CI).

### Verify

- Push a commit → GitHub Actions runs → both jobs green.

---

## Section 5: Docker and Environment

### Tasks

- [ ] Remove ChromaDB from backend `depends_on` in `docker-compose.yml` (ChromaDB is post-MVP).
- [ ] Optionally move ChromaDB service to a `docker-compose.override.yml` or Docker Compose profile.
- [ ] Verify `docker-compose up --build` starts: postgres, backend, frontend.
- [ ] Add healthcheck for backend in docker-compose:
  ```yaml
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
    interval: 30s
    timeout: 10s
    retries: 3
  ```
- [ ] Create `.env.example` with all required variables (no real secrets):
  ```env
  DATABASE_URL=postgresql+asyncpg://admin:password@localhost:5432/realestate
  GEMINI_API_KEY=your-key-here
  JWT_SECRET_KEY=change-this-secret
  NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
  # Optional (post-MVP):
  # REDIS_URL=redis://localhost:6379/0
  ```

### Verify

```powershell
docker-compose up --build -d postgres backend frontend
curl http://localhost:8000/api/v1/health
# {"status": "ok"}
docker-compose down
```

---

## Section 6: Documentation

### Tasks

- [ ] Update `README.md` quick start section with these exact commands:
  ```bash
  # 1. Start database
  docker-compose up -d postgres
  # 2. Install backend
  cd backend && pip install -r requirements.txt
  # 3. Run migrations
  cd backend && alembic upgrade head
  # 4. Load data
  python -m data_pipeline.run_pipeline --skip-crawl --input data/raw/listing_details.csv
  # 5. Generate embeddings
  python -m data_pipeline.embed
  # 6. Start backend
  cd backend && uvicorn app.main:app --reload --port 8000
  # 7. Start frontend
  cd frontend && npm install && npm run dev
  ```
- [ ] Document: MVP architecture (1 paragraph), data pipeline commands, backend/frontend dev commands.
- [ ] Document known post-MVP limitations (no rent data, no map, no price history).

### Verify

- A new developer following README can start the app and see real data.

---

## Out Of Scope (do NOT implement in Phase 4)

- Production domain and SSL setup
- Prometheus / Grafana monitoring
- Advanced rate limiting
- Coverage threshold gates (no "must have 70% coverage" rule for MVP)
- Pre-commit hooks (nice to have, not blocking)
