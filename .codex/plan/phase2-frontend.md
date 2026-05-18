# Phase 2 — Frontend MVP

> **Prerequisite:** Phase 1 complete. Backend APIs are stable and returning real data.
> **Goal:** Wire frontend pages to real backend APIs with loading/error states.
> **Timeline:** Week 3-4

---

## Section 1: API Client Setup

**Why:** All API calls go through `frontend/lib/api.ts`. Ensure it matches the actual backend endpoints.

### Tasks

- [ ] Verify `NEXT_PUBLIC_API_URL` is set in `.env` (default: `http://localhost:8000/api/v1`).
- [ ] Verify `frontend/lib/api.ts` has these functions (create if missing):
  - `getListings(params)` → `GET /api/v1/listings` with query params
  - `getListingDetail(id)` → `GET /api/v1/listings/{id}`
  - `getSimilarListings(id)` → `GET /api/v1/listings/similar/{id}`
  - `getMarketStats()` → `GET /api/v1/market/stats`
  - `getPropertyTypes()` → `GET /api/v1/market/property-types`
  - `getTopLocations()` → `GET /api/v1/market/top-locations`
  - `getPriceByDistrict()` → `GET /api/v1/market/price-by-district`
  - `login(email, password)` → `POST /api/v1/auth/login`
  - `register(data)` → `POST /api/v1/auth/register`
  - `sendChatMessage(message, sessionId?)` → `POST /api/v1/chat`
- [ ] Verify `frontend/lib/types.ts` has types matching backend Pydantic schemas (ListingCard, PaginatedResponse, MarketStats, etc.).

### Verify

```powershell
cd frontend
npx tsc --noEmit
# Should pass with no type errors in api.ts
```

---

## Section 2: Homepage

**File:** `frontend/app/page.tsx`

### Tasks

- [ ] Load market stats from `getMarketStats()` — show total listings, avg price, avg area.
- [ ] Load featured listings from `getListings({limit: 8, sort: "newest"})`.
- [ ] Load property type links from `getPropertyTypes()`.
- [ ] Show skeleton/loading state while API calls are in flight.
- [ ] Show compact error banner if any API section fails (do not crash the whole page).
- [ ] Remove any hardcoded stats or mock data.

### Verify

- Start backend: `cd backend; uvicorn app.main:app --port 8000`
- Start frontend: `cd frontend; npm run dev`
- Open `http://localhost:3000` — stats and listings should show real data.
- Stop backend → homepage should show error state, not crash.

---

## Section 3: Listing List Pages

**Files:** `frontend/app/nha-dat-ban/page.tsx`, `frontend/app/nha-dat-cho-thue/page.tsx`

### Tasks

- [ ] Wire `FilterPanel` component to API query params (listing_type, property_type, city, district, min_price, max_price, min_area, max_area, bedrooms, direction).
- [ ] Sync filter state to URL search params (so refresh preserves filters).
- [ ] Sale page (`/nha-dat-ban`): call `getListings({listing_type: "sale", ...filters})`.
- [ ] Rent page (`/nha-dat-cho-thue`): call `getListings({listing_type: "rent", ...filters})`.
  - Note: Rent data does not exist yet (only sale data crawled). Show a user-friendly empty state like "Chưa có dữ liệu cho thuê".
- [ ] Add sorting dropdown: newest, price ascending, price descending, area ascending, area descending.
- [ ] Show pagination controls using `total_pages` from API response.
- [ ] Show empty state when no results match filters.
- [ ] Show loading skeleton while fetching.

### Verify

- Open `/nha-dat-ban` — should show real sale listings.
- Apply filters → URL params update → refresh → same filters applied.
- Open `/nha-dat-cho-thue` — should show "no data" empty state.

---

## Section 4: Listing Detail Page

**File:** `frontend/app/nha-dat-ban/[id]/page.tsx`

### Tasks

- [ ] Load listing via `getListingDetail(id)`.
- [ ] Load similar listings via `getSimilarListings(id)`.
- [ ] Display: title, price, area, bedrooms, bathrooms, floors, direction, address, description, legal status, furniture, contact name, post date.
- [ ] Show similar listings section below the main listing.
- [ ] Handle missing optional fields gracefully (do not show "undefined" or break layout).
- [ ] If the listing has `latitude` and `longitude`, show a simple map marker. Otherwise, hide the map section.
- [ ] Use a clean placeholder image if no image data exists.
- [ ] Add SEO meta tags: `<title>`, `<meta description>`, Open Graph tags.

### Verify

- Open `/nha-dat-ban/1` — should show listing detail with real data.
- Open a non-existent ID like `/nha-dat-ban/99999` — should show 404 or "not found" state.

---

## Section 5: Market Dashboard

**File:** `frontend/app/thi-truong/page.tsx`

### Tasks

- [ ] Load data from existing market endpoints: stats, top-locations, price-by-district, property-types.
- [ ] Show overview stats cards (total listings, avg price, etc.).
- [ ] Show district price comparison table or bar chart (use `recharts`).
- [ ] Show property type distribution (pie or bar chart).
- [ ] Do NOT show forecast, heatmap, or ML prediction — these are post-MVP.
- [ ] Do NOT show "monthly price trends" — there is no historical data.

### Verify

- Open `/thi-truong` — should show real market data with charts.

---

## Section 6: Auth Pages

**Files:** `frontend/app/dang-nhap/page.tsx`, `frontend/app/dang-ky/page.tsx`

### Tasks

- [ ] Login page: form with email + password, calls `login()`, stores JWT token.
- [ ] Register page: form with email + password + name, calls `register()`.
- [ ] Show backend validation errors (duplicate email, wrong password, etc.).
- [ ] Redirect to homepage after successful login.
- [ ] Store JWT using the existing auth approach (localStorage or cookie).

### Verify

- Register a new user → should succeed.
- Login with that user → should get token and redirect.
- Login with wrong password → should show error message.

---

## Section 7: Chat Widget MVP

**File:** `frontend/components/chatbot/ChatWidget.tsx`

### Tasks

- [ ] Send messages via `sendChatMessage(message, sessionId)` → `POST /api/v1/chat`.
- [ ] Verify `ChatMessageResponse` from backend includes `suggested_actions` field — if not, add it to the schema.
- [ ] Show loading indicator while waiting for response.
- [ ] Render assistant response text.
- [ ] Render suggested action buttons (if any) that send a new message on click.
- [ ] Keep REST-only chat in MVP. Do NOT implement WebSocket.

### Verify

- Open any page → click chat widget → send "Tìm nhà Quận 7" → should get a response (placeholder is OK for now, will be real RAG in Phase 3).

---

## Section 8: Build Verification

### Tasks

- [ ] Run `cd frontend; npm run lint` — fix all lint errors.
- [ ] Run `cd frontend; npm run build` — fix all build errors.
- [ ] Manually check responsive layout on mobile width (375px) and desktop (1440px) using Chrome DevTools.

### Verify

```powershell
cd frontend
npm run lint
# 0 errors
npm run build
# Build succeeds
```

---

## Out Of Scope (do NOT implement in Phase 2)

- Slug-based detail routes (keep `[id]`)
- Image gallery carousel (no image data available)
- Leaflet / MapLibre map integration
- WebSocket chat streaming
- Advanced animations beyond basic skeleton/loading states
