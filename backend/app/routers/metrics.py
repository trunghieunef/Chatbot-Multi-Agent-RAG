from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select

from app.database import async_session
from app.models import Article, Chunk, Listing, PipelineRun


logger = logging.getLogger(__name__)


router = APIRouter(tags=["Metrics"])


CHAT_REQUESTS = Counter(
    "realestate_chat_requests_total",
    "Total chat completions handled by the backend",
    labelnames=("agent",),
)
RETRIEVAL_LATENCY = Histogram(
    "realestate_retrieval_latency_seconds",
    "Latency of hybrid_search pipeline",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
PIPELINE_RUNS = Gauge(
    "realestate_pipeline_runs_total",
    "Pipeline runs aggregated by DAG and status (snapshot from pipeline_runs table)",
    labelnames=("dag_id", "status"),
)
LISTINGS_TOTAL = Gauge(
    "realestate_listings_total", "Total listings in DB", labelnames=("listing_type",)
)
CHUNKS_TOTAL = Gauge(
    "realestate_chunks_total", "Total chunks indexed", labelnames=("parent_type",)
)
ARTICLES_TOTAL = Gauge(
    "realestate_articles_total", "Total articles in DB", labelnames=("category",)
)
LLM_COST_USD = Gauge(
    "realestate_llm_cost_usd",
    "Estimated LLM cost for current month (USD)",
)
LLM_BUDGET_EXCEEDED = Gauge(
    "realestate_llm_cost_budget_exceeded",
    "Whether LLM monthly budget is exceeded (1=yes, 0=no)",
)


async def _refresh_gauges() -> None:
    """Snapshot DB counts into Prometheus gauges.

    Stale label values are cleared first so deleted partitions disappear
    from `/metrics` rather than lingering at their last value.
    """
    for gauge in (LISTINGS_TOTAL, CHUNKS_TOTAL, ARTICLES_TOTAL, PIPELINE_RUNS):
        gauge.clear()

    async with async_session() as session:
        listings = await session.execute(
            select(Listing.listing_type, func.count()).group_by(Listing.listing_type)
        )
        for listing_type, count in listings.all():
            LISTINGS_TOTAL.labels(listing_type=listing_type or "unknown").set(count)

        chunks = await session.execute(
            select(Chunk.parent_type, func.count()).group_by(Chunk.parent_type)
        )
        for parent_type, count in chunks.all():
            CHUNKS_TOTAL.labels(parent_type=parent_type or "unknown").set(count)

        articles = await session.execute(
            select(Article.category, func.count()).group_by(Article.category)
        )
        for category, count in articles.all():
            ARTICLES_TOTAL.labels(category=category or "unknown").set(count)

        runs = await session.execute(
            select(PipelineRun.dag_id, PipelineRun.status, func.count()).group_by(
                PipelineRun.dag_id, PipelineRun.status
            )
        )
        for dag_id, status, count in runs.all():
            PIPELINE_RUNS.labels(dag_id=dag_id, status=status).set(count)

    # --- LLM cost from agent-service ---
    try:
        from app.services.agent_service.client import get_agent_service_client
        health = await get_agent_service_client().health()
        llm_cost = health.get("llm_cost") if isinstance(health, dict) else {}
    except Exception:
        llm_cost = {}

    if llm_cost and llm_cost.get("tracking_available"):
        LLM_COST_USD.set(float(llm_cost.get("estimated_cost_usd", 0.0)))
        LLM_BUDGET_EXCEEDED.set(1 if llm_cost.get("budget_exceeded") else 0)
    else:
        LLM_COST_USD.set(0.0)
        LLM_BUDGET_EXCEEDED.set(0)


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    """Prometheus exposition endpoint.

    Refreshes gauge snapshots from the DB on every scrape. If the DB is
    unreachable we return HTTP 503 so Prometheus marks the target down and
    operators see ``up=0`` instead of silently empty panels.
    """
    try:
        await _refresh_gauges()
    except Exception as exc:
        logger.exception("metrics scrape failed: %s", exc)
        raise HTTPException(status_code=503, detail="metrics backend unavailable")
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/health/pipeline")
async def pipeline_health() -> dict:
    """Operator-facing JSON summary of recent DAG runs.

    Returns an empty ``dags`` map when the DB is unavailable so the endpoint
    stays usable for liveness checks during outages.
    """
    summary: dict[str, dict] = {}
    try:
        async with async_session() as session:
            rows = await session.execute(
                select(
                    PipelineRun.dag_id,
                    func.max(PipelineRun.ended_at).label("last_run"),
                    PipelineRun.status,
                )
                .group_by(PipelineRun.dag_id, PipelineRun.status)
                .order_by(PipelineRun.dag_id)
            )
            runs = rows.all()
    except Exception as exc:
        logger.warning("pipeline_health DB query failed: %s", exc)
        runs = []

    for dag_id, last_run, status in runs:
        bucket = summary.setdefault(dag_id, {"successful": 0, "failed": 0, "last_run": None})
        if status == "success":
            bucket["successful"] += 1
        elif status == "failed":
            bucket["failed"] += 1
        if last_run and (bucket["last_run"] is None or last_run > bucket["last_run"]):
            bucket["last_run"] = last_run.isoformat()

    return {"as_of": datetime.now(timezone.utc).isoformat(), "dags": summary}
