import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "airflow"))

from plugins.run_metrics import build_run_summary


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
