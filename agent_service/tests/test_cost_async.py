from types import SimpleNamespace

from agent_service.llm.cost import estimate_runtime_llm_cost


def _settings(**over):
    base = dict(
        AGENT_LLM_COST_TRACKING_ENABLED=True,
        AGENT_LLM_INPUT_PRICE_PER_MILLION_USD=1.0,
        AGENT_LLM_OUTPUT_PRICE_PER_MILLION_USD=2.0,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_estimate_is_pure_and_correct():
    # 1M input @ $1 + 0.5M output @ $2 = 1 + 1 = 2.0
    amount = estimate_runtime_llm_cost(
        _settings(), input_tokens=1_000_000, output_tokens=500_000
    )
    assert amount == 2.0


def test_estimate_zero_when_tracking_disabled():
    amount = estimate_runtime_llm_cost(
        _settings(AGENT_LLM_COST_TRACKING_ENABLED=False),
        input_tokens=1_000_000, output_tokens=500_000,
    )
    assert amount == 0.0


def test_estimate_zero_when_tokens_none():
    assert estimate_runtime_llm_cost(_settings(), input_tokens=None, output_tokens=5) == 0.0
