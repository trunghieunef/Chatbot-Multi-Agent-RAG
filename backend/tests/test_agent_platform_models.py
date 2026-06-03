import importlib
from pathlib import Path

from app.database import Base
from app.models import (
    AgentLLMCall,
    AgentRetrievalEvent,
    AgentTrace,
    AgentTraceStep,
    ChatFeedback,
    EvalRun,
    EvalScore,
    MemoryProposal,
    SourceReadiness,
    UserPreference,
)

auth_chat_tables = importlib.import_module(
    "backend.alembic.versions.20260603_0009_auth_chat_tables"
)
agent_platform_tables = importlib.import_module(
    "backend.alembic.versions.20260603_0010_agent_platform_tables"
)


def test_agent_platform_models_are_registered():
    expected_tables = {
        "user_preferences",
        "memory_proposals",
        "chat_feedback",
        "agent_traces",
        "agent_trace_steps",
        "agent_llm_calls",
        "agent_retrieval_events",
        "eval_runs",
        "eval_scores",
        "source_readiness",
    }

    assert expected_tables.issubset(set(Base.metadata.tables))


def test_model_table_names_are_explicit():
    assert UserPreference.__tablename__ == "user_preferences"
    assert MemoryProposal.__tablename__ == "memory_proposals"
    assert ChatFeedback.__tablename__ == "chat_feedback"
    assert AgentTrace.__tablename__ == "agent_traces"
    assert AgentTraceStep.__tablename__ == "agent_trace_steps"
    assert AgentLLMCall.__tablename__ == "agent_llm_calls"
    assert AgentRetrievalEvent.__tablename__ == "agent_retrieval_events"
    assert EvalRun.__tablename__ == "eval_runs"
    assert EvalScore.__tablename__ == "eval_scores"
    assert SourceReadiness.__tablename__ == "source_readiness"


def test_agent_platform_migration_depends_on_auth_chat_baseline():
    assert auth_chat_tables.down_revision == "20260801_0007"
    assert agent_platform_tables.down_revision == "20260603_0009"


def test_auth_chat_baseline_migration_creates_backend_auth_chat_tables():
    migration_source = Path(auth_chat_tables.__file__).read_text(encoding="utf-8")

    assert 'op.create_table(\n        "users"' in migration_source
    assert 'op.create_table(\n        "chat_sessions"' in migration_source
    assert 'op.create_table(\n        "chat_messages"' in migration_source
