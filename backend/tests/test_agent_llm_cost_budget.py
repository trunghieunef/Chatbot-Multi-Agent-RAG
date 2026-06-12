import sys
import types

import pytest

from agent_service.config import get_agent_settings
from agent_service.llm.gemini import GeminiClient
from agent_service.llm.cost import InMemoryCostTracker


def test_monthly_budget_summary_marks_exceeded():
    tracker = InMemoryCostTracker(monthly_budget_usd=1.0)
    tracker.add_estimated_cost("2026-06", 1.25)

    summary = tracker.get_summary("2026-06")

    assert summary["budget_exceeded"] is True
    assert summary["estimated_cost_usd"] == 1.25


@pytest.mark.asyncio
async def test_budget_exceeded_skips_live_gemini_call(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("GEMINI_MODEL", "model")
    get_agent_settings.cache_clear()
    called = False

    class FakeModels:
        def generate_content(self, *, model, contents):
            nonlocal called
            called = True
            return types.SimpleNamespace(text="should not be called")

    class FakeClient:
        def __init__(self, *, api_key, http_options=None):
            self.models = FakeModels()

    monkeypatch.setitem(
        sys.modules,
        "google",
        types.SimpleNamespace(genai=types.SimpleNamespace(Client=FakeClient)),
    )
    monkeypatch.setattr(
        "agent_service.llm.gemini.get_runtime_cost_summary",
        lambda settings: {
            "budget_exceeded": True,
            "tracking_available": True,
        },
    )

    result = await GeminiClient().generate_text_with_usage("hello")

    assert result.text == ""
    assert result.skipped_reason == "llm_budget_exceeded"
    assert called is False
    get_agent_settings.cache_clear()


@pytest.mark.asyncio
async def test_live_gemini_call_requires_explicit_model(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    get_agent_settings.cache_clear()
    called = False

    class FakeModels:
        def generate_content(self, *, model, contents):
            nonlocal called
            called = True
            return types.SimpleNamespace(text="should not be called")

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setitem(
        sys.modules,
        "google",
        types.SimpleNamespace(genai=types.SimpleNamespace(Client=FakeClient)),
    )

    result = await GeminiClient().generate_text_with_usage("hello")

    assert result.text == ""
    assert result.skipped_reason == "gemini_model_not_configured"
    assert called is False
    get_agent_settings.cache_clear()


@pytest.mark.asyncio
async def test_gemini_client_passes_transport_timeout(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    get_agent_settings.cache_clear()
    seen = {}

    class FakeModels:
        def generate_content(self, *, model, contents):
            return types.SimpleNamespace(text="threaded response")

    class FakeClient:
        def __init__(self, *, api_key, http_options=None):
            seen["api_key"] = api_key
            seen["timeout"] = (
                http_options.get("timeout")
                if isinstance(http_options, dict)
                else getattr(http_options, "timeout", None)
            )
            self.models = FakeModels()

    monkeypatch.setitem(
        sys.modules,
        "google",
        types.SimpleNamespace(genai=types.SimpleNamespace(Client=FakeClient)),
    )

    result = await GeminiClient(model="model").generate_text_with_usage(
        "hello",
        timeout_seconds=1.25,
    )

    assert result.text == "threaded response"
    assert seen == {"api_key": "key", "timeout": 1250}
    get_agent_settings.cache_clear()


@pytest.mark.asyncio
async def test_usage_metadata_records_estimated_cost(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("GEMINI_MODEL", "model")
    monkeypatch.setenv("AGENT_LLM_INPUT_PRICE_PER_MILLION_USD", "0.10")
    monkeypatch.setenv("AGENT_LLM_OUTPUT_PRICE_PER_MILLION_USD", "0.40")
    get_agent_settings.cache_clear()
    recorded = {}

    class FakeModels:
        def generate_content(self, *, model, contents):
            return types.SimpleNamespace(
                text="threaded response",
                usage_metadata=types.SimpleNamespace(
                    prompt_token_count=1000,
                    candidates_token_count=2000,
                ),
            )

    class FakeClient:
        def __init__(self, *, api_key, http_options=None):
            self.models = FakeModels()

    monkeypatch.setitem(
        sys.modules,
        "google",
        types.SimpleNamespace(genai=types.SimpleNamespace(Client=FakeClient)),
    )
    monkeypatch.setattr(
        "agent_service.llm.gemini.get_runtime_cost_summary",
        lambda settings: {
            "budget_exceeded": False,
            "tracking_available": True,
        },
    )

    def fake_record(settings, *, input_tokens, output_tokens):
        recorded["input_tokens"] = input_tokens
        recorded["output_tokens"] = output_tokens
        return 0.0009

    monkeypatch.setattr(
        "agent_service.llm.gemini.record_runtime_llm_cost",
        fake_record,
    )

    result = await GeminiClient().generate_text_with_usage("hello")

    assert result.text == "threaded response"
    assert result.input_tokens == 1000
    assert result.output_tokens == 2000
    assert result.estimated_cost_usd == 0.0009
    assert recorded == {"input_tokens": 1000, "output_tokens": 2000}
    get_agent_settings.cache_clear()
