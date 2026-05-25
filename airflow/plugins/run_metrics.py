from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("PROJECT_ROOT", "/opt/project")).resolve()
BACKEND = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


def build_run_summary(
    context: dict[str, Any], *, status: str, error: str | None, metrics: dict[str, Any] | None
) -> dict[str, Any]:
    dag_run = context.get("dag_run")
    return {
        "dag_id": context["dag"].dag_id,
        "run_id": getattr(dag_run, "run_id", "unknown") if dag_run else "unknown",
        "status": status,
        "started_at": getattr(dag_run, "start_date", None) if dag_run else None,
        "ended_at": getattr(dag_run, "end_date", None) if dag_run else None,
        "metrics": metrics or {},
        "error": error,
    }


def _persist(summary: dict[str, Any]) -> None:
    import asyncio

    from app.database import async_session
    from app.models import PipelineRun
    from sqlalchemy import select

    async def _write() -> None:
        async with async_session() as session:
            existing = await session.execute(
                select(PipelineRun).where(
                    PipelineRun.dag_id == summary["dag_id"],
                    PipelineRun.run_id == summary["run_id"],
                )
            )
            run = existing.scalar_one_or_none()
            if run is None:
                run = PipelineRun(**summary)
                session.add(run)
            else:
                for key, value in summary.items():
                    setattr(run, key, value)
            await session.commit()

    asyncio.run(_write())


def on_success(context: dict[str, Any]) -> None:
    metrics: dict[str, Any] = {}
    ti = context.get("ti")
    if ti is not None and hasattr(ti, "xcom_pull"):
        for key in ("listings", "chunks", "projects", "articles", "documents", "skipped"):
            try:
                value = ti.xcom_pull(key=key)
            except Exception:
                value = None
            if value is not None:
                metrics[key] = value
    summary = build_run_summary(context, status="success", error=None, metrics=metrics)
    _persist(summary)


def on_failure(context: dict[str, Any]) -> None:
    exception = context.get("exception")
    summary = build_run_summary(
        context,
        status="failed",
        error=str(exception) if exception else None,
        metrics=None,
    )
    _persist(summary)
