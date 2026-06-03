from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, unique=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    intent = Column(String(100), nullable=True)
    agents_used = Column(JSONB, nullable=False, default=[])
    trace_summary_json = Column(JSONB, nullable=False, default={})
    full_trace_json = Column(JSONB, nullable=False, default={})
    readiness_json = Column(JSONB, nullable=False, default={})
    latency_ms = Column(Float, nullable=False, default=0.0)
    status = Column(String(30), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    graph_version = Column(String(80), nullable=True)
    prompt_version = Column(String(80), nullable=True)
    model_name = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=func.now())


class AgentTraceStep(Base):
    __tablename__ = "agent_trace_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    step_name = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False, default="success")
    latency_ms = Column(Float, nullable=False, default=0.0)
    input_json = Column(JSONB, nullable=False, default={})
    output_json = Column(JSONB, nullable=False, default={})
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())


class AgentLLMCall(Base):
    __tablename__ = "agent_llm_calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    node_name = Column(String(120), nullable=False)
    model_name = Column(String(120), nullable=False)
    prompt_version = Column(String(80), nullable=True)
    latency_ms = Column(Float, nullable=False, default=0.0)
    token_input_estimate = Column(Integer, nullable=True)
    token_output_estimate = Column(Integer, nullable=True)
    status = Column(String(30), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime, default=func.now())


class AgentRetrievalEvent(Base):
    __tablename__ = "agent_retrieval_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    tool_name = Column(String(120), nullable=False)
    parent_type = Column(String(40), nullable=True)
    filters_json = Column(JSONB, nullable=False, default={})
    result_count = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Float, nullable=False, default=0.0)
    status = Column(String(30), nullable=False, default="success")
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default={})
    created_at = Column(DateTime, default=func.now())


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(80), nullable=False, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    evaluator = Column(String(80), nullable=False, default="gemini")
    graph_version = Column(String(80), nullable=False)
    prompt_version = Column(String(80), nullable=False)
    model_name = Column(String(120), nullable=False)
    status = Column(String(30), nullable=False, default="pending")
    summary_json = Column(JSONB, nullable=False, default={})
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)


class EvalScore(Base):
    __tablename__ = "eval_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    eval_run_id = Column(Integer, ForeignKey("eval_runs.id"), nullable=False, index=True)
    metric = Column(String(80), nullable=False)
    score = Column(Float, nullable=False)
    rationale = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
