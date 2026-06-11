import uuid
from types import SimpleNamespace

import pytest

from app.models.agent_observability import (
    AgentRetrievalEvent,
    AgentTrace,
    AgentTraceStep,
)
from app.services.agent_service.contracts import AgentChatResponse, TraceSummary
from app.services.agent_service.observability import persist_agent_observability


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeObservabilitySession:
    def __init__(self):
        self.traces = []
        self.steps = []
        self.retrieval_events = []
        self.commits = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        statement_text = str(statement)
        params = getattr(statement, "compile", lambda: None)()
        request_id = None
        if params is not None:
            request_id = params.params.get("request_id_1")

        if "FROM agent_traces" in statement_text:
            trace = next(
                (item for item in self.traces if item.request_id == request_id),
                None,
            )
            return FakeScalarResult(trace)
        if "DELETE FROM agent_trace_steps" in statement_text:
            self.steps = [item for item in self.steps if item.request_id != request_id]
            return FakeScalarResult(None)
        if "DELETE FROM agent_retrieval_events" in statement_text:
            self.retrieval_events = [
                item for item in self.retrieval_events if item.request_id != request_id
            ]
            return FakeScalarResult(None)
        raise AssertionError(f"unexpected statement: {statement_text}")

    def add(self, obj):
        if isinstance(obj, AgentTrace):
            self.traces.append(obj)
        elif isinstance(obj, AgentTraceStep):
            self.steps.append(obj)
        elif isinstance(obj, AgentRetrievalEvent):
            self.retrieval_events.append(obj)
        else:
            raise AssertionError(f"unexpected add: {obj!r}")

    async def commit(self):
        self.commits += 1


@pytest.fixture()
def obs_session():
    return FakeObservabilitySession()


def _factory(session):
    return lambda: session


def _response(request_id="req-observe", steps=None, retrieval_results=None, warnings=None):
    full_trace = {}
    if steps is not None:
        full_trace["steps"] = steps
    if retrieval_results is not None:
        full_trace["retrieval_results"] = retrieval_results
    return AgentChatResponse(
        request_id=request_id,
        final_response="Answer",
        agents_used=["router", "property_search"],
        trace_summary=TraceSummary(
            intent="property_search",
            agents=["router", "property_search"],
            latency_ms=23.5,
            warnings=warnings or [],
        ),
        full_trace=full_trace,
        readiness={"property": "ready"},
    )


@pytest.mark.asyncio
async def test_replay_same_request_id_updates_trace_and_replaces_steps(obs_session):
    session_id = uuid.uuid4()
    chat_session = SimpleNamespace(id=session_id)
    user = SimpleNamespace(id=42)

    await persist_agent_observability(
        session_factory=_factory(obs_session),
        chat_session=chat_session,
        user=user,
        response=_response(
            steps=[
                {
                    "step_name": "router",
                    "status": "success",
                    "latency_ms": 1,
                    "output": {"intent": "property_search"},
                }
            ]
        ),
    )
    await persist_agent_observability(
        session_factory=_factory(obs_session),
        chat_session=chat_session,
        user=user,
        response=_response(
            steps=[
                {
                    "step_name": "router",
                    "status": "success",
                    "latency_ms": 2,
                    "output": {"intent": "investment"},
                },
                {
                    "step_name": "specialist",
                    "status": "success",
                    "latency_ms": 3,
                    "output": {"answer": "updated"},
                },
            ],
        ),
    )

    assert len(obs_session.traces) == 1
    assert obs_session.traces[0].intent == "property_search"
    assert obs_session.traces[0].session_id == session_id
    assert obs_session.traces[0].user_id == 42
    assert len(obs_session.steps) == 2
    assert [step.step_name for step in obs_session.steps] == ["router", "specialist"]
    assert obs_session.steps[0].output_json == {"intent": "investment"}
    assert obs_session.commits == 2


@pytest.mark.asyncio
async def test_two_trace_steps_create_two_step_rows(obs_session):
    await persist_agent_observability(
        session_factory=_factory(obs_session),
        chat_session=SimpleNamespace(id=uuid.uuid4()),
        user=None,
        response=_response(
            steps=[
                {"step_name": "router", "status": "success", "latency_ms": 1},
                {"step_name": "synthesizer", "status": "partial", "latency_ms": 4.5},
            ],
            warnings=["missing_market_context"],
        ),
    )

    assert [step.step_name for step in obs_session.steps] == ["router", "synthesizer"]
    assert obs_session.traces[0].status == "partial"


@pytest.mark.asyncio
async def test_retrieval_events_create_retrieval_event_rows(obs_session):
    await persist_agent_observability(
        session_factory=_factory(obs_session),
        chat_session=SimpleNamespace(id=uuid.uuid4()),
        user=None,
        response=_response(
            steps=[
                {
                    "step_name": "retriever",
                    "output": {
                        "retrieval_events": [
                            {
                                "tool_name": "hybrid_search",
                                "parent_type": "listing",
                                "filters": {"district": "Quan 2"},
                                "result_count": 3,
                                "latency_ms": 12.5,
                                "status": "success",
                                "task_id": "task-property",
                                "domain": "property",
                            }
                        ]
                    },
                }
            ],
            retrieval_results=[
                {
                    "task_id": "task-legal",
                    "domain": "legal",
                    "tool": "legal_search",
                    "status": "skipped",
                    "skip_reason": "no legal intent",
                }
            ],
        ),
    )

    assert len(obs_session.retrieval_events) == 2
    event = obs_session.retrieval_events[0]
    assert event.tool_name == "hybrid_search"
    assert event.parent_type == "listing"
    assert event.filters_json == {"district": "Quan 2"}
    assert event.result_count == 3
    assert event.metadata_json["task_id"] == "task-property"
    fallback = obs_session.retrieval_events[1]
    assert fallback.tool_name == "legal_search"
    assert fallback.status == "skipped"
    assert fallback.metadata_json["skip_reason"] == "no legal intent"


@pytest.mark.asyncio
async def test_legacy_trace_creates_trace_without_invalid_steps(obs_session):
    await persist_agent_observability(
        session_factory=_factory(obs_session),
        chat_session=SimpleNamespace(id=uuid.uuid4()),
        user=None,
        response=AgentChatResponse(
            request_id="req-legacy-observe",
            final_response="Legacy answer",
            agents_used=["unknown"],
            trace_summary=TraceSummary(intent="legacy"),
            full_trace={"mode": "legacy", "raw_sources": []},
        ),
    )

    assert len(obs_session.traces) == 1
    assert obs_session.traces[0].request_id == "req-legacy-observe"
    assert obs_session.steps == []
    assert obs_session.retrieval_events == []


@pytest.mark.asyncio
async def test_oversized_step_payloads_are_truncated(obs_session):
    oversized = {"text": "x" * 20000}

    await persist_agent_observability(
        session_factory=_factory(obs_session),
        chat_session=SimpleNamespace(id=uuid.uuid4()),
        user=None,
        response=_response(
            steps=[
                {
                    "step_name": "large_payload",
                    "input": oversized,
                    "output": oversized,
                }
            ],
        ),
    )

    step = obs_session.steps[0]
    assert len(step.input_json["truncated_json"]) <= 16384
    assert len(step.output_json["truncated_json"]) <= 16384
    assert step.input_json["truncated"] is True
    assert step.output_json["truncated"] is True
