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
