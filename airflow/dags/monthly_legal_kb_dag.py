from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import run_legal_ingestion


def _alert_emails() -> list[str]:
    raw = os.environ.get("ALERT_EMAIL_RECIPIENTS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_ARGS = {
    "owner": "data",
    "retries": 2,
    "retry_delay": timedelta(minutes=15),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "email": _alert_emails(),
    "email_on_failure": bool(_alert_emails()),
    "email_on_retry": False,
    "on_failure_callback": slack_failure_callback,
}


def _ingest_legal(**_):
    return run_legal_ingestion()


with DAG(
    dag_id="monthly_legal_kb_dag",
    description="Re-ingest changed legal PDF/HTML documents from data/knowledge/raw monthly",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 5 1 * *",
    start_date=datetime(2026, 7, 1),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "legal"],
) as dag:
    PythonOperator(task_id="ingest_legal_kb", python_callable=_ingest_legal)
