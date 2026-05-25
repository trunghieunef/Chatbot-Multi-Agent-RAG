from app.models import PipelineRun


def test_pipeline_run_columns():
    columns = {col.name for col in PipelineRun.__table__.columns}
    assert {"id", "dag_id", "run_id", "status", "started_at", "ended_at", "metrics", "error"} <= columns
