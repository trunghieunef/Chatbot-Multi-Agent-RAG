# Phase 5 — Post-MVP Backlog

> **Prerequisite:** Phase 4 complete. MVP is stable, tested, and deployable.
> **Goal:** Capture features that must NOT block MVP. Each item has a "readiness condition" — do not start until that condition is met.
> **Timeline:** After MVP is shipped.

---

## Item 1: Crawl Expansion (Rent + Project)

**Readiness:** Phase 0 sale crawl is stable and pipeline loads data without issues.

### Tasks

- [ ] Add rental listing crawl: clone `01.crawl_listing_url.py`, change `BASE_URL` to `https://batdongsan.com.vn/nha-dat-cho-thue`.
- [ ] Reuse `02.crawl_listing_details.py` for rental URLs (same page structure).
- [ ] Add `listing_type=rent` detection in data pipeline for rental listings.
- [ ] Add project crawler for `/du-an` only after project schema and API requirements are defined.
- [ ] Add news crawler only if RAG knowledge base needs it.
- [ ] Add proxy rotation only if crawls show blocking.

---

## Item 2: Scheduled Crawling

**Readiness:** Manual pipeline has run successfully multiple times without duplicates.

### Tasks

- [ ] Add APScheduler or OS cron wrapper in `data_pipeline/scheduler.py`.
- [ ] Run daily: crawl → clean → validate → load.
- [ ] Track run history: date, duration, inserted/updated/failed counts.
- [ ] Add failure notification (log or email) after retry exhaustion.

---

## Item 3: Redis Caching

**Readiness:** Query profiling shows real bottlenecks or traffic justifies cache.

### Tasks

- [ ] Cache `GET /api/v1/market/stats` (TTL: 1 hour).
- [ ] Cache common listing queries (TTL: 5-15 min).
- [ ] Invalidate cache after data pipeline load completes.
- [ ] Track cache hit ratio in logs.

---

## Item 4: WebSocket Chat Streaming

**Readiness:** REST chat is stable and RAG latency is high enough that streaming improves UX.

### Tasks

- [ ] Add `POST /api/v1/chat/ws` WebSocket endpoint.
- [ ] Stream sentence-level responses (not token-level for MVP).
- [ ] Add heartbeat and reconnect in frontend.
- [ ] Keep REST chat as fallback.

---

## Item 5: Map and Geocoding

**Readiness:** A meaningful percentage of listings have reliable lat/lng coordinates.

### Tasks

- [ ] Create `data_pipeline/geocode.py` — batch geocode from address using Nominatim (free, 1 req/sec).
- [ ] Cache address → (lat, lng) in DB.
- [ ] Add Leaflet/MapLibre map component to listing detail page.
- [ ] Add district GeoJSON boundaries from open data.
- [ ] Add choropleth heatmap only after geocoding quality is acceptable.

---

## Item 6: Price History

**Readiness:** Pipeline has collected multiple snapshots over time (at least 4+ weeks).

### Tasks

- [ ] Add `listing_price_history` table: `listing_id`, `price`, `area`, `recorded_at`.
- [ ] Record price/area changes during upsert in data pipeline.
- [ ] Use this table for trend claims in market analysis agent.

---

## Item 7: Price Prediction

**Readiness:** Historical data is large enough for train/test split by time.

### Tasks

- [ ] Train baseline model (linear regression or XGBoost).
- [ ] Features: area, bedrooms, district, property_type.
- [ ] Report MAE and error distribution.
- [ ] Add API endpoint only after model quality is acceptable.
- [ ] Add explainability (SHAP) after baseline model is useful.

---

## Explicitly NOT MVP

These items must not be implemented before Phase 4 is complete:

- Project crawler
- News crawler
- Map heatmap
- Price prediction API
- Forecast API
- SHAP explanations
- Token-level chat streaming
- Production monitoring stack (Prometheus/Grafana)
- ChromaDB as a second vector store
