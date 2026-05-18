# Phase 1 — Backend API Stabilization

> **Prerequisite:** Phase 0 complete. Database has Alembic migrations and data loaded via pipeline.
> **Goal:** Make all backend APIs stable, route-safe, and backed by real PostgreSQL data.
> **Timeline:** Week 2-3

---

## Section 1: Fix Listings Route Collision

**Why:** In `backend/app/routers/listings.py`, `/{listing_id}` (line ~130) is declared **before** `/by-product-id/{product_id}` (line ~143) and `/similar/{listing_id}` (line ~158). FastAPI matches routes in declaration order, so `/similar/1` is parsed as `listing_id="similar"` and fails with a 422.

### Tasks

- [ ] In `backend/app/routers/listings.py`, reorder the route functions so that:
  1. `GET ""` (list with filters) — stays first
  2. `GET "/by-product-id/{product_id}"` — move BEFORE `/{listing_id}`
  3. `GET "/similar/{listing_id}"` — move BEFORE `/{listing_id}`
  4. `GET "/{listing_id}"` — must be LAST among path-parameter routes

### Verify

```powershell
cd backend
uvicorn app.main:app --port 8000
# In another terminal:
curl http://localhost:8000/api/v1/listings/similar/1
# Should return similar listings JSON, NOT a 422 error
curl http://localhost:8000/api/v1/listings/by-product-id/BN12345
# Should return listing or 404, NOT 422
curl http://localhost:8000/api/v1/listings/1
# Should still return listing detail
```

---

## Section 2: Verify Listings Filters and Pagination

**Why:** Ensure all filter, sort, and pagination query params work correctly.

### Tasks

- [ ] Verify these filter params return correct results (test via browser or curl):
  - `listing_type` — `?listing_type=sale`
  - `property_type` — `?property_type=Căn hộ chung cư`
  - `city` — `?city=Hồ Chí Minh`
  - `district` — `?district=Quận 7`
  - `min_price`, `max_price` — `?min_price=2&max_price=5`
  - `min_area`, `max_area` — `?min_area=50&max_area=100`
  - `bedrooms` — `?bedrooms=2`
  - `bathrooms` — `?bathrooms=2`
  - `direction` — `?direction=Đông`
  - `search` — `?search=can ho`
- [ ] Verify sort options: `?sort=newest`, `?sort=price_asc`, `?sort=price_desc`, `?sort=area_asc`, `?sort=area_desc`.
- [ ] Verify pagination response has fields: `items`, `total`, `page`, `limit`, `total_pages`.
- [ ] Verify all queries filter by `is_active == True`.
- [ ] Verify empty results return HTTP 200 with `{"items": [], "total": 0, ...}`.

### Verify

```powershell
curl "http://localhost:8000/api/v1/listings?city=Ho+Chi+Minh&min_price=3&max_price=10&page=1&limit=5"
# Should return JSON with items array, total count, pagination
```

---

## Section 3: Market API — Real Data Only

**Why:** Market router must return real aggregate data from PostgreSQL, not mock data.

### Tasks

- [ ] Verify these endpoints return data computed from the `listings` table:
  - `GET /api/v1/market/stats` — total listings, avg price, avg area, etc.
  - `GET /api/v1/market/top-locations` — top districts by listing count.
  - `GET /api/v1/market/price-by-district` — avg price grouped by district.
  - `GET /api/v1/market/property-types` — counts by property type.
  - `GET /api/v1/market/cities` — list of cities.
  - `GET /api/v1/market/districts` — list of districts.
- [ ] Remove any endpoint that returns hardcoded or mock data.
- [ ] Do NOT expose monthly price trend claims — there is no historical data yet (single crawl snapshot).
- [ ] All aggregate queries must filter by `is_active == True`.

### Verify

```powershell
curl http://localhost:8000/api/v1/market/stats
# Should return {"total_listings": N, "avg_price": N, ...} with real numbers > 0
```

---

## Section 4: Auth Flow Verification

**Why:** Auth endpoints must work for frontend integration.

### Tasks

- [ ] Verify `POST /api/v1/auth/register` creates a user with bcrypt-hashed password.
- [ ] Verify `POST /api/v1/auth/login` returns `{"access_token": "...", "token_type": "bearer"}`.
- [ ] Verify requests with valid `Authorization: Bearer <token>` header are accepted by protected routes.
- [ ] Verify invalid credentials return `401 Unauthorized`, not a 500 error.
- [ ] Verify duplicate email registration returns a clear error.

### Verify

```powershell
# Register
curl -X POST http://localhost:8000/api/v1/auth/register -H "Content-Type: application/json" -d "{\"email\":\"test@test.com\",\"password\":\"test1234\",\"full_name\":\"Test\"}"
# Login
curl -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json" -d "{\"email\":\"test@test.com\",\"password\":\"test1234\"}"
# Should return access_token
```

---

## Section 5: Backend Smoke Tests

**Why:** Automated tests catch regressions before frontend integration.

### Tasks

- [ ] Create `backend/tests/` directory with `__init__.py` and `conftest.py`.
- [ ] In `conftest.py`: set up test database (SQLite in-memory or test PostgreSQL) with dependency override for `get_db`.
- [ ] Create `backend/tests/test_health.py` — test `GET /api/v1/health` returns 200.
- [ ] Create `backend/tests/test_listings.py`:
  - Test `GET /api/v1/listings` returns paginated response.
  - Test `GET /api/v1/listings/1` returns listing or 404.
  - Test `GET /api/v1/listings/similar/1` returns list.
- [ ] Create `backend/tests/test_market.py` — test `GET /api/v1/market/stats` returns 200.
- [ ] Create `backend/tests/test_auth.py` — test register + login flow.
- [ ] Install pytest and httpx: add `pytest`, `httpx` to `backend/requirements.txt`.

### Verify

```powershell
cd backend
pip install -r requirements.txt
pytest tests -v
# All tests should pass
python -m compileall app
# No syntax errors
```

---

## Out Of Scope (do NOT implement in Phase 1)

- Cursor-based pagination (use offset/limit for MVP)
- Redis caching
- Full-text search indexes (keep current ILIKE search)
- Monthly / quarterly price trends
- WebSocket chat
- New API endpoints beyond those listed above
