import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "airflow"))

from plugins.alerting import build_failure_payload


def test_build_failure_payload_contains_dag_and_task_ids():
    context = {
        "dag": type("D", (), {"dag_id": "daily_listings_dag"})(),
        "task_instance": type("T", (), {"task_id": "crawl_sale_urls", "log_url": "http://airflow/log"})(),
        "execution_date": "2026-06-02T02:00:00+07:00",
    }

    payload = build_failure_payload(context)

    assert "daily_listings_dag" in payload["text"]
    assert "crawl_sale_urls" in payload["text"]
    assert "http://airflow/log" in payload["text"]
