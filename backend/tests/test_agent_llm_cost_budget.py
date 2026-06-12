from agent_service.llm.cost import InMemoryCostTracker


def test_monthly_budget_exceeded_forces_deterministic():
    tracker = InMemoryCostTracker(monthly_budget_usd=1.0)
    tracker.add_estimated_cost("2026-06", 1.25)

    summary = tracker.get_summary("2026-06")

    assert summary["budget_exceeded"] is True
    assert summary["estimated_cost_usd"] == 1.25
