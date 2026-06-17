from __future__ import annotations

import pytest

from agent_service.contracts import AgentChatRequest
from agent_service.graph.synthesis import format_investment_scorecard


def _committee_review() -> dict:
    return {
        "recommendation": {
            "decision": "need_more_info",
            "confidence": "low",
            "rationale": "Need rent and legal confirmation.",
            "required_confirmations": [
                "expected_monthly_rent",
                "legal_documents",
            ],
        },
        "perspectives": [
            {
                "role": "bull",
                "summary": "Gia/m2 co the hop ly neu benchmark dung.",
                "suggested_actions": ["So sanh them listing"],
            },
            {
                "role": "bear",
                "summary": "Dong tien chua chac chan.",
                "suggested_actions": ["Xac nhan tien thue"],
            },
        ],
    }


def _investment_assumptions() -> dict:
    return {
        "loan_ratio": {
            "value": 0.6,
            "unit": "ratio_0_1",
            "source": "default",
            "note": "loan_ratio resolved from default.",
        },
        "expected_monthly_rent": {
            "value": None,
            "unit": "vnd_per_month",
            "source": "default",
            "note": "Expected monthly rent is missing.",
        },
    }


def _investment_metrics() -> dict:
    return {
        "price_per_m2": {
            "value": 64.0,
            "unit": "million_vnd_per_m2",
            "confidence": "high",
            "warnings": [],
        },
        "metric_warnings": {
            "warnings": ["missing_expected_monthly_rent"],
        },
    }


def test_format_investment_scorecard_includes_scorecard_assumptions_and_checklist():
    response = format_investment_scorecard(
        committee_review=_committee_review(),
        investment_assumptions=_investment_assumptions(),
        investment_metrics=_investment_metrics(),
    )

    assert "Scorecard dau tu" in response
    assert "need_more_info" in response
    assert "64.0 million_vnd_per_m2" in response
    assert "loan_ratio=0.6" in response
    assert "Checklist hanh dong" in response
    assert "khong phai loi khuyen tai chinh" in response


@pytest.mark.asyncio
async def test_synthesizer_node_uses_scorecard_when_committee_review_exists():
    from agent_service.graph import nodes

    result = await nodes.synthesizer_node(
        {
            "request": AgentChatRequest(
                request_id="req-scorecard",
                session_id="session-scorecard",
                message="Co nen dau tu can ho nay?",
            ),
            "agents_to_run": ["investment_advisor"],
            "agent_results": {
                "investment_advisor": {
                    "content": "Fallback specialist content.",
                    "warnings": [],
                    "evidence_ids_used": [],
                }
            },
            "committee_review": _committee_review(),
            "investment_assumptions": _investment_assumptions(),
            "investment_metrics": _investment_metrics(),
            "evidence_by_id": {},
            "evidence_for_agent": {},
            "warnings": [],
            "trace_steps": [],
            "force_deterministic": True,
        }
    )

    assert result["final_response"].startswith("Scorecard dau tu")
    assert "Fallback specialist content" not in result["final_response"]
    assert result["suggested_actions"] == [
        "Xac nhan tien thue ky vong",
        "Xac nhan ty le vay va lai suat",
        "Kiem tra phap ly",
    ]


@pytest.mark.asyncio
async def test_synthesizer_node_keeps_scorecard_when_llm_synthesis_is_enabled(
    monkeypatch,
):
    from agent_service.config import AgentSettings
    from agent_service.graph import nodes

    class FakeGeminiClient:
        async def generate_json(self, *_args, **_kwargs):
            return {
                "final_response": "LLM overwrite",
                "suggested_actions": ["LLM action"],
                "claims": [{"type": "disclaimer", "text": "safe"}],
                "evidence_ids_used": [],
            }

    monkeypatch.setattr(
        nodes,
        "get_agent_settings",
        lambda: AgentSettings(AGENT_SPECIALIST_LLM_ENABLED=True),
    )
    monkeypatch.setattr(nodes, "GeminiClient", FakeGeminiClient)

    result = await nodes.synthesizer_node(
        {
            "request": AgentChatRequest(
                request_id="req-scorecard-llm",
                session_id="session-scorecard",
                message="Co nen dau tu can ho nay?",
            ),
            "agents_to_run": ["investment_advisor"],
            "agent_results": {},
            "committee_review": _committee_review(),
            "investment_assumptions": _investment_assumptions(),
            "investment_metrics": _investment_metrics(),
            "evidence_by_id": {},
            "evidence_for_agent": {},
            "warnings": [],
            "trace_steps": [],
            "force_deterministic": False,
        }
    )

    assert result["final_response"].startswith("Scorecard dau tu")
    assert "LLM overwrite" not in result["final_response"]
    assert result["suggested_actions"] == [
        "Xac nhan tien thue ky vong",
        "Xac nhan ty le vay va lai suat",
        "Kiem tra phap ly",
    ]
