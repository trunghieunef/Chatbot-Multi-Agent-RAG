from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Response
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


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    try:
        await _refresh_gauges()
    except Exception:  # DB unavailable — still serve registry contents.
        pass
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/health/pipeline")
async def pipeline_health() -> dict:
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
    except Exception:
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
