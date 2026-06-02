import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "airflow"))

from plugins.run_metrics import build_run_summary, collect_metrics_from_dag_run


def test_build_run_summary_extracts_dag_run_status():
    context = {
        "dag": type("D", (), {"dag_id": "daily_listings_dag"})(),
        "dag_run": type(
            "R",
            (),
            {
                "run_id": "manual__2026-08-01T02:00:00",
                "start_date": __import__("datetime").datetime(2026, 8, 1, 2, 0),
                "end_date": __import__("datetime").datetime(2026, 8, 1, 2, 30),
                "state": "success",
            },
        )(),
        "ti": type("T", (), {"xcom_pull": lambda self, key=None, task_ids=None: None})(),
    }

    summary = build_run_summary(context, status="success", error=None, metrics={"listings": 42, "chunks": 168})

    assert summary["dag_id"] == "daily_listings_dag"
    assert summary["run_id"].startswith("manual__")
    assert summary["status"] == "success"
    assert summary["metrics"] == {"listings": 42, "chunks": 168}
    assert summary["error"] is None


def _fake_ti(task_id: str, return_value):
    """Build a fake TaskInstance whose xcom_pull returns the ingestor dict."""

    class _TI:
        def __init__(self):
            self.task_id = task_id

        def xcom_pull(self, task_ids=None, key=None):  # noqa: ARG002
            if task_ids == self.task_id:
                return return_value
            return None

    return _TI()


def _fake_dag_run(task_instances):
    class _DR:
        def get_task_instances(self):
            return task_instances

    return _DR()


def test_collect_metrics_from_dag_run_aggregates_return_value_xcoms():
    context = {
        "dag_run": _fake_dag_run(
            [
                _fake_ti("ingest_sale", {"listings": 10, "chunks": 30}),
                _fake_ti("ingest_rent", {"listings": 5, "chunks": 12}),
                _fake_ti("crawl", "ignored-non-dict"),
            ]
        ),
    }

    metrics = collect_metrics_from_dag_run(context)

    assert metrics == {"listings": 15, "chunks": 42}


def test_collect_metrics_from_dag_run_aggregates_listing_publish_metrics():
    context = {
        "dag_run": _fake_dag_run(
            [
                _fake_ti(
                    "ingest_sale",
                    {
                        "published": 10,
                        "indexed": 8,
                        "chunks": 30,
                        "publish_errors": 1,
                        "index_errors": 2,
                    },
                ),
                _fake_ti(
                    "ingest_rent",
                    {
                        "published": 5,
                        "indexed": 5,
                        "chunks": 12,
                        "publish_errors": 0,
                        "index_errors": 1,
                    },
                ),
            ]
        ),
    }

    metrics = collect_metrics_from_dag_run(context)

    assert metrics == {
        "published": 15,
        "indexed": 13,
        "chunks": 42,
        "publish_errors": 1,
        "index_errors": 3,
    }


def test_collect_metrics_from_dag_run_returns_empty_when_no_dag_run():
    assert collect_metrics_from_dag_run({}) == {}


def test_collect_metrics_from_dag_run_ignores_unknown_keys():
    context = {
        "dag_run": _fake_dag_run(
            [_fake_ti("x", {"listings": 1, "irrelevant": 99})]
        ),
    }

    metrics = collect_metrics_from_dag_run(context)

    assert metrics == {"listings": 1}
