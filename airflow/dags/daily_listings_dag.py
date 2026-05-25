from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.utils.task_group import TaskGroup

from plugins.alerting import slack_failure_callback
from plugins.pipeline_runner import (
    REPO_ROOT,
    run_crawler,
    run_listings_ingestion,
)


def _alert_emails() -> list[str]:
    raw = os.environ.get("ALERT_EMAIL_RECIPIENTS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


DEFAULT_ARGS = {
    "owner": "data",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "email": _alert_emails(),
    "email_on_failure": bool(_alert_emails()),
    "email_on_retry": False,
    "on_failure_callback": slack_failure_callback,
}


def _last_crawl_var(source: str) -> str:
    return f"last_{source}_crawl_at"


def _read_since(source: str) -> str | None:
    return Variable.get(_last_crawl_var(source), default_var=None)


def _store_now(source: str, **_) -> None:
    Variable.set(_last_crawl_var(source), datetime.utcnow().date().isoformat())


def _crawl_urls(source: str, base_module: str, **_):
    since = _read_since(source)
    output = str(REPO_ROOT / f"data/raw/{source}_urls.csv")
    args = {"--pages": ["1", "30"], "--output": output, "--workers": "4"}
    if since:
        args["--since"] = since
    run_crawler(module=f"{base_module}.crawl_urls", args=args)


def _crawl_details(source: str, base_module: str, **_):
    input_csv = str(REPO_ROOT / f"data/raw/{source}_urls.csv")
    output_csv = str(REPO_ROOT / f"data/raw/{source}_details.csv")
    run_crawler(
        module=f"{base_module}.crawl_details",
        args={"--input": input_csv, "--output": output_csv, "--workers": "4"},
    )


def _ingest(source: str, **_):
    csv_path = str(REPO_ROOT / f"data/raw/{source}_details.csv")
    return run_listings_ingestion(csv_path, batch_size=50)


with DAG(
    dag_id="daily_listings_dag",
    description="Crawl + ingest sale and rent listings daily, then deactivate expired listings",
    default_args=DEFAULT_ARGS,
    schedule_interval="0 2 * * *",
    start_date=datetime(2026, 5, 25),
    catchup=False,
    max_active_runs=1,
    tags=["realestate", "listings"],
) as dag:
    source_groups = []
    for source, base_module in (("sale", "crawler.sale"), ("rent", "crawler.rent")):
        with TaskGroup(group_id=source) as group:
            crawl_urls = PythonOperator(
                task_id=f"crawl_{source}_urls",
                python_callable=_crawl_urls,
                op_kwargs={"source": source, "base_module": base_module},
            )
            crawl_details = PythonOperator(
                task_id=f"crawl_{source}_details",
                python_callable=_crawl_details,
                op_kwargs={"source": source, "base_module": base_module},
            )
            ingest = PythonOperator(
                task_id=f"ingest_{source}",
                python_callable=_ingest,
                op_kwargs={"source": source},
            )
            mark_done = PythonOperator(
                task_id=f"mark_{source}_done",
                python_callable=_store_now,
                op_kwargs={"source": source},
            )
            crawl_urls >> crawl_details >> ingest >> mark_done
        source_groups.append(group)

    mark_active = PostgresOperator(
        task_id="mark_active",
        postgres_conn_id="realestate_app",
        sql="""
            UPDATE listings
               SET is_active = false,
                   updated_at = NOW()
             WHERE is_active = true
               AND expiry_date IS NOT NULL
               AND expiry_date <> ''
               AND (
                    -- expiry_date stored as 'DD/MM/YYYY'
                    CASE WHEN expiry_date ~ '^\\d{2}/\\d{2}/\\d{4}$'
                         THEN to_date(expiry_date, 'DD/MM/YYYY') < CURRENT_DATE
                         WHEN expiry_date ~ '^\\d{4}-\\d{2}-\\d{2}$'
                         THEN to_date(expiry_date, 'YYYY-MM-DD') < CURRENT_DATE
                         ELSE false
                    END
               );
        """,
    )

    for group in source_groups:
        group >> mark_active
