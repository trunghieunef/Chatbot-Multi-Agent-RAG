---
paths:
  - backend/app/routers/**/*
  - backend/app/schemas/**/*
  - frontend/lib/api.ts
---
# API Endpoints

All routes prefixed with `/api/v1/`.

## Listings
- `GET /api/v1/listings` — list + filter + pagination
- `GET /api/v1/listings/{id}` — detail
- `GET /api/v1/listings/search` — full-text search
- `GET /api/v1/listings/similar/{id}` — similar listings (vector similarity)

## Market
- `GET /api/v1/market/stats` — aggregate statistics
- `GET /api/v1/market/price-trends` — price trends by area/time
- `GET /api/v1/market/heatmap` — heatmap data

## Chat
- `POST /api/v1/chat` — send message (REST)
- `WS /api/v1/chat/ws` — WebSocket real-time
- `GET /api/v1/chat/sessions` — chat history
- `GET /api/v1/chat/sessions/{id}` — session detail

## Auth
- `POST /api/v1/auth/register` — register
- `POST /api/v1/auth/login` — login (JWT)

## System
- `GET /api/v1/health` — health check
