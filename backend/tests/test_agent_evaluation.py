import pytest
from fastapi.testclient import TestClient

from agent_service.config import get_agent_settings
from agent_service.main import app


@pytest.fixture(autouse=True)
def clear_agent_settings_cache():
    get_agent_settings.cache_clear()
    yield
    get_agent_settings.cache_clear()


def test_build_judge_prompt_includes_metrics_and_versions():
    from agent_service.evaluation.judge import METRICS, build_judge_prompt

    prompt = build_judge_prompt(
        question="Can ho nao gan metro o Thu Duc?",
        answer="Can ho A gan tuyen metro va co phap ly ro rang.",
        sources=[
            {
                "type": "listing",
                "title": "Can ho A",
                "url": "https://example.test/listing-a",
            }
        ],
        trace={"agents": ["property_search"], "latency_ms": 12},
        graph_version="graph-test-v9",
        prompt_version="prompt-test-v9",
        model_name="judge-test-model",
    )

    for metric in METRICS:
        assert metric in prompt
    assert "groundedness" in prompt
    assert "citation_quality" in prompt
    assert "graph-test-v9" in prompt
    assert "prompt-test-v9" in prompt
    assert "judge-test-model" in prompt
    assert "Can ho nao gan metro o Thu Duc?" in prompt
    assert "Can ho A" in prompt
    assert '"agents"' in prompt


def test_fallback_scores_marks_all_metrics_skipped_with_reason():
    from agent_service.evaluation.judge import METRICS, fallback_scores

    result = fallback_scores("judge disabled")

    assert result["status"] == "skipped"
    assert set(result["scores"]) == set(METRICS)
    assert result["scores"]["groundedness"]["score"] == 0.0
    for score in result["scores"].values():
        assert score["score"] == 0.0
        assert "judge disabled" in score["rationale"]


@pytest.mark.asyncio
async def test_judge_answer_returns_completed_scores_from_client():
    from agent_service.evaluation.judge import judge_answer

    class FakeClient:
        async def generate_json(self, prompt):
            assert "groundedness" in prompt
            return {
                "scores": {
                    "groundedness": {
                        "score": 0.8,
                        "rationale": "Answer cites retrieved listing facts.",
                    }
                }
            }

    result = await judge_answer(
        question="Tim can ho Quan 7",
        answer="Can ho A o Quan 7 phu hop.",
        sources=[{"title": "Can ho A"}],
        trace={"agents": ["property_search"]},
        graph_version="graph-v9",
        prompt_version="prompt-v9",
        model_name="judge-model",
        client=FakeClient(),
    )

    assert result == {
        "status": "completed",
        "scores": {
            "groundedness": {
                "score": 0.8,
                "rationale": "Answer cites retrieved listing facts.",
            }
        },
    }


@pytest.mark.asyncio
async def test_judge_answer_falls_back_when_client_returns_empty():
    from agent_service.evaluation.judge import judge_answer

    class EmptyClient:
        async def generate_json(self, prompt):
            assert "JSON" in prompt
            return {}

    result = await judge_answer(
        question="Tim can ho Quan 7",
        answer="Can ho A o Quan 7 phu hop.",
        sources=[],
        trace={},
        graph_version="graph-v9",
        prompt_version="prompt-v9",
        model_name="judge-model",
        client=EmptyClient(),
    )

    assert result["status"] == "skipped"
    assert result["scores"]["groundedness"]["score"] == 0.0
    assert "empty judge response" in result["scores"]["groundedness"]["rationale"]


def test_internal_evaluate_requires_agent_key(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    client = TestClient(app)

    response = client.post(
        "/internal/agent/evaluate",
        json={"question": "Tim nha", "answer": "Can ho A"},
    )

    assert response.status_code == 401


def test_internal_evaluate_uses_default_versions_and_model(monkeypatch):
    monkeypatch.setenv("AGENT_INTERNAL_KEY", "secret-test-key")
    monkeypatch.setenv("AGENT_GRAPH_VERSION", "graph-default-v9")
    monkeypatch.setenv("AGENT_PROMPT_VERSION", "prompt-default-v9")
    monkeypatch.setenv("GEMINI_JUDGE_MODEL", "judge-default-v9")
    seen = {}

    async def fake_judge_answer(**kwargs):
        seen.update(kwargs)
        return {"status": "completed", "scores": {"groundedness": {"score": 1.0}}}

    monkeypatch.setattr("agent_service.main.judge_answer", fake_judge_answer, raising=False)
    client = TestClient(app)

    response = client.post(
        "/internal/agent/evaluate",
        headers={"X-Internal-Agent-Key": "secret-test-key"},
        json={
            "question": "Can ho nao gan metro?",
            "answer": "Can ho A gan metro.",
            "sources": [{"title": "Can ho A"}],
            "trace": {"agents": ["property_search"]},
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert seen["question"] == "Can ho nao gan metro?"
    assert seen["answer"] == "Can ho A gan metro."
    assert seen["sources"] == [{"title": "Can ho A"}]
    assert seen["trace"] == {"agents": ["property_search"]}
    assert seen["graph_version"] == "graph-default-v9"
    assert seen["prompt_version"] == "prompt-default-v9"
    assert seen["model_name"] == "judge-default-v9"
