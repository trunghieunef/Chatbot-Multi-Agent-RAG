from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text, func

from app.database import Base


class PipelineRun(Base):
    """Summary record per Airflow DAG run."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dag_id = Column(String(80), nullable=False)
    run_id = Column(String(160), nullable=False)
    status = Column(String(20), nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    metrics = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    __table_args__ = (
        Index("ix_pipeline_runs_dag_run", "dag_id", "run_id", unique=True),
        Index("ix_pipeline_runs_started", "started_at"),
    )
