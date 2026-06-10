from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel, Field

from pipeline_worker import maintenance, runner
from pipeline_worker.security import require_internal_key


app = FastAPI(
    title="Real Estate Pipeline Worker",
    version="0.1.0",
    description="Internal service for crawl, ingest, chunk, embed, and pipeline maintenance jobs.",
)


class CrawlerRequest(BaseModel):
    module: str
    args: dict[str, Any] = Field(default_factory=dict)
    timeout: int = 7200


class CsvIngestRequest(BaseModel):
    csv_path: str
    batch_size: int = 50


class CleanupChunksRequest(BaseModel):
    retention_days: int = 60


@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/internal/pipeline/health", tags=["Internal Pipeline"])
def internal_health() -> dict[str, str]:
    return {"status": "ok", "service": "pipeline-worker"}


@app.post("/internal/pipeline/crawler", tags=["Internal Pipeline"])
def run_crawler(
    payload: CrawlerRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = runner.run_module(payload.module, payload.args, timeout=payload.timeout)
    return {"stdout": completed.stdout, "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/listings", tags=["Internal Pipeline"])
def ingest_listings(
    payload: CsvIngestRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = runner.run_module(
        "data_pipeline.ingestors.listings_ingestor",
        {"--csv": payload.csv_path, "--batch-size": str(payload.batch_size)},
    )
    return {"result": runner.parse_result(completed.stdout), "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/projects", tags=["Internal Pipeline"])
def ingest_projects(
    payload: CsvIngestRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = runner.run_module(
        "data_pipeline.ingestors.projects_ingestor",
        {"--csv": payload.csv_path, "--batch-size": str(payload.batch_size)},
    )
    return {"result": runner.parse_result(completed.stdout), "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/news", tags=["Internal Pipeline"])
def ingest_news(
    payload: CsvIngestRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = runner.run_module(
        "data_pipeline.ingestors.news_ingestor",
        {"--csv": payload.csv_path, "--batch-size": str(payload.batch_size)},
    )
    return {"result": runner.parse_result(completed.stdout), "stderr": completed.stderr}


@app.post("/internal/pipeline/ingest/legal", tags=["Internal Pipeline"])
def ingest_legal(
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    completed = runner.run_module("data_pipeline.ingestors.legal_kb_ingestor", {})
    return {"result": runner.parse_result(completed.stdout), "stderr": completed.stderr}


@app.post("/internal/pipeline/maintenance/deactivate-expired-listings", tags=["Internal Pipeline"])
async def deactivate_expired_listings(
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    return {"result": await maintenance.deactivate_expired_listings()}


@app.post("/internal/pipeline/maintenance/cleanup-expired-listing-chunks", tags=["Internal Pipeline"])
async def cleanup_expired_listing_chunks(
    payload: CleanupChunksRequest,
    x_internal_agent_key: str | None = Header(default=None, alias="X-Internal-Agent-Key"),
) -> dict[str, Any]:
    require_internal_key(x_internal_agent_key)
    return {"result": await maintenance.cleanup_expired_listing_chunks(payload.retention_days)}
