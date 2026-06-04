import pytest

from agent_service.agents.specialists import (
    run_investment_agent,
    run_legal_agent,
    run_property_agent,
)


@pytest.mark.asyncio
async def test_property_agent_requires_evidence_for_listing_claims():
    result = await run_property_agent(
        query="Tim can ho Quan 7",
        evidence=[
            {
                "id": 1,
                "title": "Can ho Quan 7",
                "district": "Quan 7",
                "city": "Ho Chi Minh",
                "price_text": "4.8 ty",
                "area_text": "70 m2",
                "url": "https://example.test/1",
            }
        ],
        preferences={},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["agent_name"] == "property_search"
    assert "Can ho Quan 7" in result["content"]
    assert result["sources"][0]["type"] == "listing"
    assert result["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_legal_agent_warns_when_legal_kb_not_ready():
    result = await run_legal_agent(
        query="Sang ten so do can gi",
        evidence=[],
        preferences={},
        readiness={"legal": {"status": "not_ready"}},
    )

    assert result["agent_name"] == "legal_advisor"
    assert "chua san sang" in result["content"].lower()
    assert result["warnings"]


@pytest.mark.asyncio
async def test_investment_agent_includes_financial_disclaimer():
    result = await run_investment_agent(
        query="Dau tu can ho Quan 7",
        evidence=[],
        preferences={"risk_preferences": {"value": "conservative"}},
        readiness={"listings": {"status": "ready"}},
    )

    assert result["agent_name"] == "investment_advisor"
    assert "khong phai loi khuyen tai chinh" in result["content"].lower()
