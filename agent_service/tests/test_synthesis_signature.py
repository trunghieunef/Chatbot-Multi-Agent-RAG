from __future__ import annotations

import pytest

from agent_service.graph.synthesis import synthesize_final_answer


@pytest.mark.asyncio
async def test_synthesis_accepts_plan_and_evidence_map_and_rejects_fabricated_ids():
    captured = {}

    async def fake_generate_json(prompt, *, timeout_seconds=None):
        captured["prompt"] = prompt
        # Model fabricates an evidence id not in the allowed set.
        return {
            "final_response": "Giá khu vực là 50 tr/m².",
            "suggested_actions": ["So sánh thêm"],
            "claims": [{"text": "Giá 50 tr/m²", "evidence_ids": ["ev_999"]}],
            "evidence_ids_used": ["ev_999"],
        }

    result = await synthesize_final_answer(
        query="giá quận 7?",
        conversation_context=[],
        agent_results={"market_analysis": {"status": "completed", "content": "x",
                                           "evidence_ids_used": ["ev_1"]}},
        deterministic_response="Phản hồi dự phòng.",
        default_actions=["Tìm BĐS"],
        generate_json=fake_generate_json,
        timeout_seconds=5.0,
        allowed_evidence_ids={"ev_1"},
        supervisor_plan={"selected_agents": ["market_analysis"], "intent": "market_analysis"},
        evidence_by_id={"ev_1": {"metric": "avg_price_per_m2", "value": 48}},
    )
    assert result.used_llm is False                      # fabricated id rejected
    assert result.final_response == "Phản hồi dự phòng."
    assert "market_analysis" in captured["prompt"]       # plan reached the prompt
