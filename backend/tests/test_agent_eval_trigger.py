import asyncio
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.agent_observability import EvalRun, EvalScore
from app.routers import chat
from app.schemas.chat import ChatMessageRequest
from app.services.agent_service.client import AgentServiceError
from app.services.agent_service.contracts import AgentChatResponse, TraceSummary
from app.services.agent_service.observability import mark_stale_eval_runs_failed


class FakeDB:
    def __init__(self):
        self.added = []
        self.commit_count = 0

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, query):
        if "count(" in str(query).lower():
            return SimpleNamespace(scalar=lambda: 0)
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    async def flush(self):
        for obj in self.added:
            if obj.__class__.__name__ == "ChatSession" and obj.id is None:
                obj.id = uuid.uuid4()
            if obj.__class__.__name__ == "ChatMessage" and obj.created_at is None:
                obj.created_at = datetime(2026, 1, 1)

    async def commit(self):
        self.commit_count += 1


class FakeEvalSession:
    def __init__(self):
        self.eval_runs = []
        self.eval_scores = []
        self.commit_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj):
        if isinstance(obj, EvalRun):
            self.eval_runs.append(obj)
        elif isinstance(obj, EvalScore):
            self.eval_scores.append(obj)
        else:
            raise AssertionError(f"unexpected add: {obj!r}")

    async def flush(self):
        for index, run in enumerate(self.eval_runs, start=1):
            if run.id is None:
                run.id = index

    async def execute(self, statement):
        statement_text = str(statement)
        if "FROM eval_runs" not in statement_text:
            raise AssertionError(f"unexpected statement: {statement_text}")
        compiled = statement.compile()
        run_id = compiled.params.get("id_1")
        run = next((item for item in self.eval_runs if item.id == run_id), None)
        return SimpleNamespace(scalar_one_or_none=lambda: run)

    async def commit(self):
        self.commit_count += 1


class FakeAgentClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.evaluate_payload = None

    async def evaluate(self, payload):
        self.evaluate_payload = payload
        if self.error:
            raise self.error
        return self.response


class FakeCleanupDB:
    def __init__(self, runs):
        self.runs = runs
        self.commit_count = 0

    async def execute(self, statement):
        cutoff = statement.compile().params["created_at_1"]
        rows = [
            run
            for run in self.runs
            if run.status == "pending" and run.created_at < cutoff
        ]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    async def commit(self):
        self.commit_count += 1


def _settings(**overrides):
    values = {
        "CHATBOT_EVAL_ENABLED": False,
        "CHATBOT_EVAL_SAMPLE_RATE": 0.0,
        "CHATBOT_EVAL_SYNC_FOR_TESTS": False,
        "CHATBOT_AGENT_SERVICE_ENABLED": True,
        "CHATBOT_TRACE_LEVEL": "full",
        "CHAT_ABUSE_GUARD_ENABLED": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _agent_response(request_id="req-eval"):
    return AgentChatResponse(
        request_id=request_id,
        final_response="Agent answer",
        agents_used=["router", "property_search"],
        sources=[{"type": "listing", "product_id": "hf-1"}],
        trace_summary=TraceSummary(
            intent="property_search",
            agents=["router", "property_search"],
            source_count=1,
            latency_ms=10,
        ),
        full_trace={
            "mode": "agent_service",
            "graph_version": "graph-v7",
            "prompt_version": "prompt-v3",
            "model_name": "gemini-test",
            "steps": [{"step_name": "router", "status": "success"}],
        },
    )


def test_should_schedule_eval_disabled_false():
    assert (
        chat.should_schedule_eval(
            enabled=False,
            sample_rate=1.0,
            answer="Answer",
            mode=None,
        )
        is False
    )


@pytest.mark.parametrize("mode", ["agent_service_error", "legacy_pipeline", "legacy"])
def test_should_schedule_eval_skips_fallback_modes(mode):
    assert (
        chat.should_schedule_eval(
            enabled=True,
            sample_rate=1.0,
            answer="Answer",
            mode=mode,
        )
        is False
    )


def test_should_schedule_eval_skips_empty_answer_and_respects_sample_bounds():
    assert chat.should_schedule_eval(enabled=True, sample_rate=1.0, answer="", mode=None) is False
    assert chat.should_schedule_eval(enabled=True, sample_rate=0.0, answer="Answer", mode=None) is False
    assert chat.should_schedule_eval(enabled=True, sample_rate=1.0, answer="Answer", mode=None) is True


def test_sampled_eval_completes_and_persists_scores(monkeypatch):
    eval_session = FakeEvalSession()
    agent_response = _agent_response()
    client = FakeAgentClient(
        response={
            "status": "completed",
            "summary": {"verdict": "good"},
            "scores": {
                "groundedness": {"score": 0.9, "rationale": "Cites sources"},
                "helpfulness": 0.8,
            },
        }
    )

    async def run_pipeline(*args):
        return agent_response

    monkeypatch.setattr(
        chat,
        "get_settings",
        lambda: _settings(
            CHATBOT_EVAL_ENABLED=True,
            CHATBOT_EVAL_SAMPLE_RATE=1.0,
            CHATBOT_EVAL_SYNC_FOR_TESTS=True,
        ),
    )
    monkeypatch.setattr(chat, "_run_agent_service_pipeline", run_pipeline)
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args: None)
    monkeypatch.setattr(chat, "get_agent_service_client", lambda: client)
    monkeypatch.setattr(chat, "async_session", lambda: eval_session)

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha Quan 2"),
            user=None,
            db=FakeDB(),
        )
    )

    assert response.content == "Agent answer"
    assert len(eval_session.eval_runs) == 1
    run = eval_session.eval_runs[0]
    assert run.request_id == agent_response.request_id
    assert run.status == "completed"
    assert run.evaluator == "gemini"
    assert run.graph_version == "graph-v7"
    assert run.prompt_version == "prompt-v3"
    assert run.model_name == "gemini-test"
    assert run.summary_json == {"verdict": "good"}
    assert {score.metric: score.score for score in eval_session.eval_scores} == {
        "groundedness": 0.9,
        "helpfulness": 0.8,
    }
    assert client.evaluate_payload["question"] == "Tim nha Quan 2"
    assert client.evaluate_payload["answer"] == "Agent answer"
    assert client.evaluate_payload["sources"][0]["product_id"] == "hf-1"
    assert client.evaluate_payload["trace"]["graph_version"] == "graph-v7"
    assert client.evaluate_payload["graph_version"] == "graph-v7"
    assert client.evaluate_payload["prompt_version"] == "prompt-v3"
    assert client.evaluate_payload["model_name"] == "gemini-test"


def test_eval_failure_does_not_fail_chat_and_marks_run_failed(monkeypatch):
    eval_session = FakeEvalSession()
    client = FakeAgentClient(error=AgentServiceError("service unavailable"))

    async def run_pipeline(*args):
        return _agent_response()

    monkeypatch.setattr(
        chat,
        "get_settings",
        lambda: _settings(
            CHATBOT_EVAL_ENABLED=True,
            CHATBOT_EVAL_SAMPLE_RATE=1.0,
            CHATBOT_EVAL_SYNC_FOR_TESTS=True,
        ),
    )
    monkeypatch.setattr(chat, "_run_agent_service_pipeline", run_pipeline)
    monkeypatch.setattr(chat, "persist_agent_observability", lambda *args: None)
    monkeypatch.setattr(chat, "get_agent_service_client", lambda: client)
    monkeypatch.setattr(chat, "async_session", lambda: eval_session)

    response = asyncio.run(
        chat.send_message(
            ChatMessageRequest(message="Tim nha Quan 2"),
            user=None,
            db=FakeDB(),
        )
    )

    assert response.content == "Agent answer"
    assert eval_session.eval_runs[0].status == "failed"
    assert eval_session.eval_runs[0].error_message == "AgentServiceError"


@pytest.mark.asyncio
async def test_stale_pending_eval_runs_are_marked_failed():
    now = datetime.utcnow()
    stale = EvalRun(
        request_id="stale",
        graph_version="graph",
        prompt_version="prompt",
        model_name="model",
        status="pending",
        created_at=now - timedelta(minutes=11),
    )
    recent = EvalRun(
        request_id="recent",
        graph_version="graph",
        prompt_version="prompt",
        model_name="model",
        status="pending",
        created_at=now - timedelta(minutes=2),
    )
    completed = EvalRun(
        request_id="completed",
        graph_version="graph",
        prompt_version="prompt",
        model_name="model",
        status="completed",
        created_at=now - timedelta(minutes=20),
    )
    db = FakeCleanupDB([stale, recent, completed])

    count = await mark_stale_eval_runs_failed(db)

    assert count == 1
    assert stale.status == "failed"
    assert stale.error_message == "eval_timeout_stale"
    assert recent.status == "pending"
    assert completed.status == "completed"
    assert db.commit_count == 1
