from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(os.environ.get("PROJECT_ROOT", "/opt/project")).resolve()
BACKEND = REPO_ROOT / "backend"
for path in (str(REPO_ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


logger = logging.getLogger(__name__)


_METRIC_KEYS = ("listings", "chunks", "projects", "articles", "documents", "skipped")


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


def collect_metrics_from_dag_run(context: dict[str, Any]) -> dict[str, Any]:
    """Pull ingestor return-value XComs from every task instance in the run.

    DAG-level callbacks do not receive ``ti`` in their context; the metrics
    have to be assembled from ``dag_run.get_task_instances()``. PythonOperator
    stores its callable's return value under the implicit ``return_value``
    key, so we pull that and merge any keys we recognize.
    """
    dag_run = context.get("dag_run")
    if dag_run is None or not hasattr(dag_run, "get_task_instances"):
        return {}

    metrics: dict[str, Any] = {}
    try:
        task_instances = dag_run.get_task_instances()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("failed to enumerate task instances for metrics: %s", exc)
        return {}

    for ti in task_instances:
        try:
            value = ti.xcom_pull(task_ids=ti.task_id)
        except Exception:
            continue
        if not isinstance(value, dict):
            continue
        for key in _METRIC_KEYS:
            if key in value and isinstance(value[key], (int, float)):
                metrics[key] = metrics.get(key, 0) + value[key]
    return metrics


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

    try:
        asyncio.run(_write())
    except Exception as exc:
        # Observability writes must never break a successful task run. Log
        # loudly so the SRE sees it, but swallow the error here.
        logger.exception("pipeline_runs persist failed: %s", exc)


def on_success(context: dict[str, Any]) -> None:
    metrics = collect_metrics_from_dag_run(context)
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
