# Phase 4B — Market Intelligence & Map Analytics

Goal: price comparison dashboard, price prediction model, interactive map with heatmap
Timeline: Week 7-9 (parallel with Phase 4 optimization)

---

## Market Comparison Engine

### Price Comparison API (`backend/app/routers/market.py`)

- `GET /api/v1/market/compare?districts=Quan7,Quan2,ThuDuc`
  - Avg price/m2 per district
  - Median price, min, max, listing count
  - Property type breakdown per district
  - Month-over-month change (%)
- `GET /api/v1/market/compare/property-types?city=HCM`
  - Avg price by property type (apartment vs house vs land)
  - Area distribution per type
- `GET /api/v1/market/ranking`
  - Top 10 cheapest/most expensive districts
  - Top 10 highest supply areas
  - Top 10 fastest price growth

### Comparison Service (`backend/app/services/market_service.py`)

- SQL aggregate queries: AVG, MEDIAN, PERCENTILE on price/area
- Group by: city, district, property_type, listing_type
- Time series: price trends by month (requires post_date data)
- Cache results in Redis (TTL 1 hour)

---

## Price Prediction

### Data Preparation

- Features: area_m2, bedrooms, bathrooms, floors, district, city, property_type, direction
- Target: price_billion
- Clean: drop rows with missing price or area
- Encode categoricals: district -> one-hot or target encoding
- Train/test split: 80/20 by time (post_date)

### Model (`backend/app/services/price_predictor.py`)

- Approach 1 (simple, ship fast): XGBoost / LightGBM
  - Train on historical listing data
  - Feature importance for explainability
  - RMSE, MAE, R2 metrics
- Approach 2 (if enough time-series data): Prophet / ARIMA
  - Monthly avg price per district
  - Forecast next 3-6 months
  - Confidence intervals
- Model saved as pickle/joblib in `backend/models/`
- Retrain weekly via scheduler or on-demand

### Prediction API

- `POST /api/v1/market/predict-price`
  - Input: area, bedrooms, district, property_type
  - Output: predicted_price, confidence_range, comparable_listings
- `GET /api/v1/market/forecast?district=Quan7&months=6`
  - Output: monthly predicted avg price, trend direction, confidence bands
- `GET /api/v1/market/price-factors?district=Quan7`
  - Output: feature importance (what drives price in this area)

### Explainability

- SHAP values for individual predictions
- "Why this price?" explanation text
- Comparable listings used for reference
- Disclaimer: prediction is estimate, not guarantee

---

## Interactive Map

### Backend Map Data API

- `GET /api/v1/map/listings?bounds=lat1,lng1,lat2,lng2`
  - Return listings within map viewport
  - Clustered at zoom < 14, individual markers at zoom >= 14
  - Fields: id, lat, lng, price, area, property_type, title
- `GET /api/v1/map/heatmap?metric=price_per_m2`
  - Aggregated by district/ward
  - Metrics: avg price/m2, listing density, price change %
  - Return GeoJSON polygons with metric values
- `GET /api/v1/map/districts?city=HCM`
  - District boundaries as GeoJSON
  - Per-district stats: avg price, count, trend

### Frontend Map Components

#### Listing Map (`components/map/ListingMap.tsx`)

- Leaflet or MapLibre GL JS
- Marker clusters (react-leaflet-markercluster)
- Click marker -> popup with listing mini card
- Popup: title, price, area, link to detail page
- Filter sync: map moves -> update listing results

#### Heatmap Layer (`components/map/PriceHeatmap.tsx`)

- Choropleth map: districts colored by avg price/m2
- Color scale: green (cheap) -> yellow -> red (expensive)
- Toggle metrics: price/m2, listing count, price change %
- Hover district -> tooltip with stats
- Click district -> zoom in + show listings

#### Price Comparison Map (`components/map/ComparisonMap.tsx`)

- Split view or overlay: compare 2-3 districts side by side
- Bar chart overlay on map per district
- Timeline slider: see how prices changed over months

#### Prediction Map (`components/map/ForecastMap.tsx`)

- Districts colored by predicted price trend (up/down/stable)
- Arrow indicators for growth direction
- Click district -> show forecast chart (line chart, 6 months)
- Confidence bands visualization

### Map Pages

#### Market Dashboard Update (`app/thi-truong/page.tsx`)

- Tab 1: Overview stats + charts (existing)
- Tab 2: Interactive heatmap (new)
- Tab 3: Price comparison tool (new)
- Tab 4: Price forecast (new)

#### Comparison Page (`app/thi-truong/so-sanh/page.tsx`)

- Select 2-4 districts to compare
- Side-by-side stats table
- Overlaid price trend charts
- Map highlighting selected districts

#### Forecast Page (`app/thi-truong/du-doan/page.tsx`)

- District selector
- Property type filter
- Input: area, bedrooms -> predicted price
- Forecast chart with confidence bands
- Feature importance bar chart
- "What-if" sliders (change area/rooms -> see price change)

---

## Geocoding

### Batch Geocoding (`data_pipeline/geocode.py`)

- Listings without lat/lng -> geocode from address
- Nominatim (free, rate-limited: 1 req/sec)
- Fallback: Google Geocoding API (paid, fast)
- Cache results: address -> (lat, lng) in DB
- Run as pipeline step after clean, before load
- Store lat/lng in listings table

### District Boundaries

- Download Vietnam district GeoJSON from open data
- Store in `data/geo/districts.geojson`
- Load to API for choropleth rendering
- Match listings to districts by lat/lng point-in-polygon

---

## Dependencies

- Python: `xgboost` or `lightgbm`, `scikit-learn`, `shap`, `joblib`
- Frontend: `leaflet`, `react-leaflet`, `react-leaflet-markercluster`
- Data: Vietnam district GeoJSON boundaries
- Geocoding: Nominatim API (free) or Google Geocoding API key

---

## Deliverables

- Price comparison API (compare districts, property types)
- Price prediction model (XGBoost/LightGBM)
- Prediction API with explainability
- Interactive map with listing markers + clusters
- Heatmap choropleth by avg price/m2
- Price forecast visualization
- Geocoded listings (lat/lng)

## Verification

- `GET /api/v1/market/compare?districts=Quan7,Quan2` -> returns comparison data
- `POST /api/v1/market/predict-price` with area=80, bedrooms=2, district=Quan7 -> reasonable price
- `GET /api/v1/market/forecast?district=Quan7&months=6` -> returns monthly forecast
- Map loads with markers at correct positions
- Heatmap colors districts correctly by price
- Prediction R2 > 0.7 on test set
- Comparison page renders side-by-side charts
