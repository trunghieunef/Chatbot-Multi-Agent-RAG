"""
Real Estate Chatbot API v2 — FastAPI Application.

Main entry point that wires together all routers,
middleware, and startup/shutdown events.
"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import async_session, init_db
from app.routers import admin, articles, auth, chat, listings, market, metrics, preferences, projects
from app.services.agent_service.observability import mark_stale_eval_runs_failed


settings = get_settings()
logger = logging.getLogger(__name__)


async def _observability_cleanup_loop() -> None:
    while True:
        try:
            async with async_session() as db:
                await mark_stale_eval_runs_failed(db)
        except Exception:
            logger.exception("Observability cleanup failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup: create tables (dev only, use Alembic in prod)
    await init_db()
    print("[OK] Database tables initialized")
    cleanup_task = None
    if settings.OBSERVABILITY_CLEANUP_ENABLED:
        cleanup_task = asyncio.create_task(_observability_cleanup_loop())
    try:
        yield
    finally:
        if cleanup_task is not None:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
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
app.include_router(projects.router, prefix="/api/v1")
app.include_router(articles.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(preferences.memory_router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")
if settings.CHATBOT_ADMIN_ENABLED:
    app.include_router(admin.router, prefix="/api/v1")


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
