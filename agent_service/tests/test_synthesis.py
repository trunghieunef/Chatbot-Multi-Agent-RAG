from __future__ import annotations

import pytest

from agent_service.graph.synthesis import build_synthesis_prompt, synthesize_final_answer


def test_synthesis_prompt_forbids_renaming_listings():
    """The prose must name listings using the exact titles from the agent
    outputs, never inventing project names or borrowing names from earlier
    conversation turns — otherwise the answer text disagrees with the source
    cards (which show the real DB titles)."""
    prompt = build_synthesis_prompt(
        query="tìm căn hộ 2 phòng ngủ",
        conversation_context=[{"role": "user", "content": "Iconia Lakeside"}],
        agent_results={},
    )
    lowered = prompt.lower()
    assert "exact" in lowered and "title" in lowered
    assert "conversation context" in lowered  # explicitly tells it not to reuse names from there


@pytest.mark.asyncio
async def test_synthesize_final_answer_uses_llm_when_valid():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {
            "final_response": "Ket luan tong hop tu nhieu agent.",
            "suggested_actions": ["Xem listing", "Kiem tra phap ly"],
        }

    result = await synthesize_final_answer(
        query="Can ho nay co nen mua khong?",
        conversation_context=[],
        agent_results={
            "property_search": {"content": "Listing phu hop."},
            "legal_advisor": {"content": "Can kiem tra so hong."},
        },
        deterministic_response="Listing phu hop.\n\nCan kiem tra so hong.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
    )

    assert result.final_response == "Ket luan tong hop tu nhieu agent."
    assert result.suggested_actions == ["Xem listing", "Kiem tra phap ly"]
    assert result.used_llm is True


@pytest.mark.asyncio
async def test_synthesize_final_answer_falls_back_on_invalid_payload():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {"bad": "payload"}

    result = await synthesize_final_answer(
        query="Can ho nay co nen mua khong?",
        conversation_context=[],
        agent_results={"property_search": {"content": "Listing phu hop."}},
        deterministic_response="Listing phu hop.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
    )

    assert result.final_response == "Listing phu hop."
    assert result.suggested_actions == ["So sanh lua chon"]
    assert result.used_llm is False
    assert "synthesizer_invalid_json" in result.warnings


@pytest.mark.asyncio
async def test_synthesize_final_answer_accepts_grounded_llm_claims():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {
            "final_response": "Can ho A phu hop voi bang chung da thu thap.",
            "suggested_actions": ["Xem listing"],
            "claims": [
                {
                    "type": "fact",
                    "text": "Can ho A phu hop voi nhu cau.",
                    "evidence_ids": ["ev1"],
                }
            ],
            "evidence_ids_used": ["ev1"],
        }

    result = await synthesize_final_answer(
        query="Can ho A co phu hop khong?",
        conversation_context=[],
        agent_results={"property_search": {"content": "Can ho A phu hop."}},
        deterministic_response="Can ho A phu hop.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
        allowed_evidence_ids={"ev1"},
    )

    assert result.final_response == "Can ho A phu hop voi bang chung da thu thap."
    assert result.suggested_actions == ["Xem listing"]
    assert result.used_llm is True


@pytest.mark.asyncio
async def test_synthesize_final_answer_rejects_unvalidated_evidence_ids():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {
            "final_response": "Can ho A chac chan tang gia manh.",
            "suggested_actions": ["Dat coc ngay"],
            "claims": [
                {
                    "type": "fact",
                    "text": "Can ho A se tang gia manh.",
                    "evidence_ids": ["ev_fake"],
                }
            ],
            "evidence_ids_used": ["ev_fake"],
        }

    result = await synthesize_final_answer(
        query="Can ho A co dang dau tu khong?",
        conversation_context=[],
        agent_results={"investment_advisor": {"content": "Can so sanh them ROI."}},
        deterministic_response="Can so sanh them ROI.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
        allowed_evidence_ids={"ev1"},
    )

    assert result.final_response == "Can so sanh them ROI."
    assert result.suggested_actions == ["So sanh lua chon"]
    assert result.used_llm is False
    assert "synthesizer_invalid_evidence" in result.warnings


@pytest.mark.asyncio
async def test_synthesize_final_answer_requires_claims_when_evidence_is_available():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {
            "final_response": "Can ho A phu hop.",
            "suggested_actions": ["Xem listing"],
        }

    result = await synthesize_final_answer(
        query="Can ho A co phu hop khong?",
        conversation_context=[],
        agent_results={"property_search": {"content": "Can ho A phu hop."}},
        deterministic_response="Can ho A phu hop.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
        allowed_evidence_ids={"ev1"},
    )

    assert result.final_response == "Can ho A phu hop."
    assert result.suggested_actions == ["So sanh lua chon"]
    assert result.used_llm is False
    assert "synthesizer_missing_claims" in result.warnings


@pytest.mark.asyncio
async def test_synthesize_final_answer_rejects_factual_claims_when_no_evidence_is_allowed():
    async def fake_generate_json(prompt: str, *, timeout_seconds=None):
        return {
            "final_response": "Can ho A chac chan tang gia vi thi truong tot.",
            "suggested_actions": ["Dat coc ngay"],
            "claims": [
                {
                    "type": "fact",
                    "text": "Can ho A chac chan tang gia.",
                    "evidence_ids": ["ev_fake"],
                }
            ],
            "evidence_ids_used": ["ev_fake"],
        }

    result = await synthesize_final_answer(
        query="Can ho A co dang dau tu khong?",
        conversation_context=[],
        agent_results={"investment_advisor": {"content": "Chua co du bang chung ROI."}},
        deterministic_response="Chua co du bang chung ROI.",
        default_actions=["So sanh lua chon"],
        generate_json=fake_generate_json,
        timeout_seconds=1.0,
        allowed_evidence_ids=set(),
    )

    assert result.final_response == "Chua co du bang chung ROI."
    assert result.suggested_actions == ["So sanh lua chon"]
    assert result.used_llm is False
    assert "synthesizer_missing_allowed_evidence" in result.warnings
