"""
Real Estate Chatbot API v2 — FastAPI Application.

Main entry point that wires together all routers,
middleware, and startup/shutdown events.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import init_db
from app.routers import listings, market, auth, chat


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: create tables (dev only, use Alembic in prod)
    await init_db()
    print("[OK] Database tables initialized")
    yield
    # Shutdown: cleanup
    print("[BYE] Application shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Nền tảng tư vấn bất động sản tích hợp chatbot multi-agent RAG",
    lifespan=lifespan,
)

# ─── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───────────────────────────────────────────────────
app.include_router(listings.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")


# ─── Health check ─────────────────────────────────────────────
@app.get("/api/v1/health", tags=["System"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["System"])
async def root():
    return {
        "message": "Real Estate Chatbot API v2",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
