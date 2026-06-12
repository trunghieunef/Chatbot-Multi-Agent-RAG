import pytest

from agent_service.agents.llm_specialists import (
    run_llm_or_deterministic_specialist,
)


@pytest.mark.asyncio
async def test_invalid_llm_specialist_json_falls_back_to_deterministic():
    async def deterministic_runner(**kwargs):
        return {
            "agent_name": "investment_advisor",
            "status": "no_evidence",
            "content": "Chua co du bang chung de tra loi.",
            "evidence_ids_used": [],
            "warnings": [],
        }

    async def invalid_json(prompt: str):
        return {}

    result = await run_llm_or_deterministic_specialist(
        agent_name="investment_advisor",
        deterministic_runner=deterministic_runner,
        query="co nen mua khong",
        evidence=[],
        preferences={},
        readiness={},
        generate_json=invalid_json,
    )

    assert result["status"] == "no_evidence"
    assert result["content"] == "Chua co du bang chung de tra loi."
    assert "llm_specialist_invalid_json" in result["warnings"]
