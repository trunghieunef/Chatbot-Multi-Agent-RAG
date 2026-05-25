from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import REPO_ROOT, run_crawler, run_news_ingestion


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


def _crawl_news(**_):
    run_crawler(
        module="crawler.news.crawl_articles",
        args={
            "--pages": ["1", "10"],
            "--output": str(REPO_ROOT / "data/raw/news_articles.csv"),
            "--workers": "2",
        },
    )


def _ingest_news(**_):
    return run_news_ingestion(str(REPO_ROOT / "data/raw/news_articles.csv"))


with DAG(
    dag_id="weekly_news_dag",
    description="Crawl + ingest real estate news weekly",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 4 * * 0",
    start_date=datetime(2026, 5, 25),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "news"],
) as dag:
    crawl = PythonOperator(task_id="crawl_news", python_callable=_crawl_news)
    ingest = PythonOperator(task_id="ingest_news", python_callable=_ingest_news)
    crawl >> ingest
