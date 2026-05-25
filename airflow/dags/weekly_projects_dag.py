from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import REPO_ROOT, run_crawler, run_projects_ingestion


def _alert_emails() -> list[str]:
    raw = os.environ.get("ALERT_EMAIL_RECIPIENTS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_ARGS = {
    "owner": "data",
    "retries": 3,
    "retry_delay": timedelta(minutes=10),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "email": _alert_emails(),
    "email_on_failure": bool(_alert_emails()),
    "email_on_retry": False,
    "on_failure_callback": slack_failure_callback,
}


def _crawl_project_urls(**_):
    output = str(REPO_ROOT / "data/raw/projects_urls.csv")
    run_crawler(
        module="crawler.projects.crawl_urls",
        args={"--pages": ["1", "20"], "--output": output, "--workers": "3"},
    )


def _crawl_project_details(**_):
    run_crawler(
        module="crawler.projects.crawl_details",
        args={
            "--input": str(REPO_ROOT / "data/raw/projects_urls.csv"),
            "--output": str(REPO_ROOT / "data/raw/projects_details.csv"),
            "--workers": "3",
        },
    )


def _ingest_projects(**_):
    return run_projects_ingestion(str(REPO_ROOT / "data/raw/projects_details.csv"))


with DAG(
    dag_id="weekly_projects_dag",
    description="Crawl + ingest real estate projects weekly",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 3 * * 0",
    start_date=datetime(2026, 5, 25),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "projects"],
) as dag:
    crawl_urls = PythonOperator(task_id="crawl_project_urls", python_callable=_crawl_project_urls)
    crawl_details = PythonOperator(task_id="crawl_project_details", python_callable=_crawl_project_details)
    ingest = PythonOperator(task_id="ingest_projects", python_callable=_ingest_projects)
    crawl_urls >> crawl_details >> ingest
