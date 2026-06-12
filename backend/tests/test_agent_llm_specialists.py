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


@pytest.mark.asyncio
async def test_llm_specialist_uses_specialist_timeout():
    async def deterministic_runner(**kwargs):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "deterministic",
            "evidence_ids_used": ["ev1"],
            "warnings": [],
        }

    seen = {}

    async def valid_json(prompt: str, *, timeout_seconds=None):
        seen["timeout_seconds"] = timeout_seconds
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "llm",
            "claims": [
                {"type": "fact", "text": "llm", "evidence_ids": ["ev1"]},
            ],
            "evidence_ids_used": ["ev1"],
            "confidence": "medium",
            "warnings": [],
            "missing_evidence": [],
        }

    await run_llm_or_deterministic_specialist(
        agent_name="property_search",
        deterministic_runner=deterministic_runner,
        query="tim can ho",
        evidence=[{"evidence_id": "ev1"}],
        preferences={},
        readiness={},
        generate_json=valid_json,
        timeout_seconds=2.5,
    )

    assert seen["timeout_seconds"] == 2.5


@pytest.mark.asyncio
async def test_empty_claims_llm_specialist_falls_back_to_deterministic():
    async def deterministic_runner(**kwargs):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "deterministic grounded answer",
            "evidence_ids_used": ["ev1"],
            "warnings": [],
        }

    async def empty_claims_json(prompt: str, *, timeout_seconds=None):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "unsupported persuasive answer",
            "claims": [],
            "evidence_ids_used": ["ev1"],
            "confidence": "medium",
            "warnings": [],
            "missing_evidence": [],
        }

    result = await run_llm_or_deterministic_specialist(
        agent_name="property_search",
        deterministic_runner=deterministic_runner,
        query="tim can ho",
        evidence=[{"evidence_id": "ev1"}],
        preferences={},
        readiness={},
        generate_json=empty_claims_json,
    )

    assert result["content"] == "deterministic grounded answer"
    assert "llm_specialist_missing_claims" in result["warnings"]


@pytest.mark.asyncio
async def test_empty_claims_and_no_used_ids_falls_back_when_evidence_available():
    async def deterministic_runner(**kwargs):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "deterministic grounded answer",
            "evidence_ids_used": ["ev1"],
            "warnings": [],
        }

    async def empty_grounding_json(prompt: str, *, timeout_seconds=None):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "unsupported persuasive answer",
            "claims": [],
            "evidence_ids_used": [],
            "confidence": "medium",
            "warnings": [],
            "missing_evidence": [],
        }

    result = await run_llm_or_deterministic_specialist(
        agent_name="property_search",
        deterministic_runner=deterministic_runner,
        query="tim can ho",
        evidence=[{"evidence_id": "ev1"}],
        preferences={},
        readiness={},
        generate_json=empty_grounding_json,
    )

    assert result["content"] == "deterministic grounded answer"
    assert "llm_specialist_missing_claims" in result["warnings"]
