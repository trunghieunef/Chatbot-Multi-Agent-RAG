from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def build_failure_payload(context: dict[str, Any]) -> dict:
    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    log_url = getattr(context["task_instance"], "log_url", "")
    execution_date = context.get("execution_date", "?")
    return {
        "text": (
            f":rotating_light: Airflow task failed\n"
            f"DAG: `{dag_id}`\n"
            f"Task: `{task_id}`\n"
            f"Run: `{execution_date}`\n"
            f"Logs: {log_url}"
        )
    }


def slack_failure_callback(context: dict[str, Any]) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    payload = build_failure_payload(context)
    try:
        httpx.post(webhook, json=payload, timeout=10).raise_for_status()
    except Exception as exc:
        logger.warning("slack failure callback failed: %s", exc)
