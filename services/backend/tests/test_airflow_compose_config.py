from pathlib import Path


def test_airflow_pythonpath_can_import_plugins_package():
    compose = Path("etl/airflow/docker-compose.airflow.yml").read_text(encoding="utf-8")

    assert "PYTHONPATH: /opt/airflow:/opt/project" in compose
    assert "- ./plugins:/opt/airflow/plugins" in compose

