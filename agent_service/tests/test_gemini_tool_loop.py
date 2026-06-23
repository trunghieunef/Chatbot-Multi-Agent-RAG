from __future__ import annotations

import types as pytypes
import pytest

from agent_service.llm import gemini


class _FakeFunctionCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _FakeResponse:
    def __init__(self, function_calls=None, text=""):
        self.function_calls = function_calls or []
        self.text = text
        self.usage_metadata = pytypes.SimpleNamespace(
            prompt_token_count=10, candidates_token_count=5
        )


class _FakeModels:
    def __init__(self, responses):
        self._responses = list(responses)

    def generate_content(self, **kwargs):
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.models = _FakeModels(responses)


def _patch_cost_tracking_available(monkeypatch):
    """Make cost tracking report 'available, under budget' so the guards in
    run_tool_loop / generate_text_with_usage do not short-circuit offline
    (no Redis in the test environment)."""
    monkeypatch.setattr(
        gemini,
        "get_runtime_cost_summary",
        lambda settings: {"tracking_available": True, "budget_exceeded": False},
        raising=False,
    )


@pytest.mark.asyncio
async def test_run_tool_loop_executes_tool_then_returns_text(monkeypatch):
    _patch_cost_tracking_available(monkeypatch)
    # First model turn: ask for a tool. Second turn: final text.
    responses = [
        _FakeResponse(function_calls=[_FakeFunctionCall("search_listings", {"query": "q"})]),
        _FakeResponse(text="Đã tìm thấy 1 căn phù hợp."),
    ]
    monkeypatch.setattr(
        gemini.genai, "Client", lambda **kw: _FakeClient(responses), raising=False
    )

    calls = []

    async def executor(name, args):
        calls.append((name, args))
        return {"status": "success", "results": [{"id": 1, "title": "Căn A"}]}

    client = gemini.GeminiClient(api_key="k", model="gemini-2.5-flash")
    result = await client.run_tool_loop(
        system_prompt="role",
        user_message="Tìm căn hộ",
        function_declarations=[{"name": "search_listings"}],
        executor=executor,
        max_iterations=3,
        timeout_seconds=5.0,
    )

    assert result.text == "Đã tìm thấy 1 căn phù hợp."
    assert [s.tool_name for s in result.steps] == ["search_listings"]
    assert result.steps[0].result["results"][0]["id"] == 1
    assert calls == [("search_listings", {"query": "q"})]


@pytest.mark.asyncio
async def test_run_tool_loop_skips_without_api_key():
    client = gemini.GeminiClient(api_key="", model="gemini-2.5-flash")

    async def executor(name, args):
        raise AssertionError("executor must not run without api key")

    result = await client.run_tool_loop(
        system_prompt="role", user_message="x",
        function_declarations=[{"name": "t"}], executor=executor,
        max_iterations=2, timeout_seconds=5.0,
    )
    assert result.skipped_reason == "no_api_key"
    assert result.text == ""
    assert result.steps == []


@pytest.mark.asyncio
async def test_run_tool_loop_skips_when_cost_tracking_unavailable(monkeypatch):
    # Cost tracking enabled but the cost summary reports tracking is unavailable
    # (e.g. Redis unreachable) => the loop must skip and never call the executor.
    monkeypatch.setattr(
        gemini,
        "get_runtime_cost_summary",
        lambda settings: {"tracking_available": False},
        raising=False,
    )
    monkeypatch.setattr(
        gemini.genai,
        "Client",
        lambda **kw: (_ for _ in ()).throw(AssertionError("client must not be built")),
        raising=False,
    )

    async def executor(name, args):
        raise AssertionError("executor must not run when cost tracking unavailable")

    client = gemini.GeminiClient(api_key="k", model="gemini-2.5-flash")
    assert client.settings.AGENT_LLM_COST_TRACKING_ENABLED is True
    result = await client.run_tool_loop(
        system_prompt="role",
        user_message="x",
        function_declarations=[{"name": "t"}],
        executor=executor,
        max_iterations=2,
        timeout_seconds=5.0,
    )
    assert result.skipped_reason == "llm_cost_tracking_unavailable"
    assert result.text == ""
    assert result.steps == []
    assert result.iterations == 0


@pytest.mark.asyncio
async def test_generate_text_runs_with_api_key_even_if_model_is_default(monkeypatch):
    _patch_cost_tracking_available(monkeypatch)
    responses = [_FakeResponse(text="ok")]
    monkeypatch.setattr(gemini.genai, "Client", lambda **kw: _FakeClient(responses), raising=False)
    # model passed positionally => model_explicitly_configured True historically,
    # but we assert behavior holds when only api_key is provided.
    client = gemini.GeminiClient(api_key="k", model="gemini-2.5-flash")
    monkeypatch.setattr(client, "model_explicitly_configured", False, raising=False)
    out = await client.generate_text("hi")
    assert out == "ok"
