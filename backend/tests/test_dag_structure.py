import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AIRFLOW_DIR = REPO_ROOT / "airflow"


@pytest.fixture(scope="module")
def dagbag():
    pytest.importorskip("airflow.models")

    if str(AIRFLOW_DIR) not in sys.path:
        sys.path.insert(0, str(AIRFLOW_DIR))

    os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "false")
    os.environ.setdefault("PROJECT_ROOT", str(REPO_ROOT))

    from airflow.models import DagBag

    return DagBag(dag_folder=str(AIRFLOW_DIR / "dags"), include_examples=False)


def test_no_import_errors(dagbag):
    assert dagbag.import_errors == {}, dagbag.import_errors


def test_expected_dags_loaded(dagbag):
    expected = {
        "daily_listings_dag",
        "weekly_projects_dag",
        "weekly_news_dag",
        "monthly_legal_kb_dag",
    }
    assert expected.issubset(dagbag.dags.keys())


def test_daily_listings_has_sale_and_rent_groups(dagbag):
    dag = dagbag.dags["daily_listings_dag"]
    task_ids = {task.task_id for task in dag.tasks}
    assert "sale.crawl_sale_urls" in task_ids
    assert "sale.ingest_sale" in task_ids
    assert "rent.crawl_rent_urls" in task_ids
    assert "rent.ingest_rent" in task_ids
    assert "mark_active" in task_ids


def test_mark_active_runs_after_both_groups(dagbag):
    dag = dagbag.dags["daily_listings_dag"]
    mark_active = dag.get_task("mark_active")
    upstream_ids = {task.task_id for task in mark_active.upstream_list}
    assert "sale.mark_sale_done" in upstream_ids
    assert "rent.mark_rent_done" in upstream_ids


def test_daily_listings_ingest_runs_after_crawl_details(dagbag):
    dag = dagbag.dags["daily_listings_dag"]

    for source in ("sale", "rent"):
        crawl_details = dag.get_task(f"{source}.crawl_{source}_details")
        ingest = dag.get_task(f"{source}.ingest_{source}")
        mark_done = dag.get_task(f"{source}.mark_{source}_done")

        assert ingest in crawl_details.downstream_list
        assert mark_done in ingest.downstream_list


def test_retry_policy_applied(dagbag):
    dag = dagbag.dags["weekly_projects_dag"]
    for task in dag.tasks:
        assert task.retries == 3
        assert task.retry_exponential_backoff is True


def test_monthly_legal_kb_dag_loaded(dagbag):
    dag = dagbag.dags.get("monthly_legal_kb_dag")
    assert dag is not None
    task_ids = {task.task_id for task in dag.tasks}
    assert "ingest_legal_kb" in task_ids
