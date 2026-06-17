from __future__ import annotations

import pytest

from agent_service.config import get_agent_settings
from agent_service.contracts import AgentChatRequest
from agent_service.graph import nodes
from agent_service.graph import retrieval_planner
from agent_service.graph.router import RouterDecision
from agent_service.graph.workflow import run_agent_graph


def test_agent_react_settings_default_to_disabled(monkeypatch):
    from agent_service.config import AgentSettings

    monkeypatch.delenv("AGENT_REACT_ENABLED", raising=False)
    monkeypatch.delenv("AGENT_REACT_MAX_ITERATIONS", raising=False)
    monkeypatch.delenv("AGENT_REACT_CONTROLLER_MODE", raising=False)
    monkeypatch.delenv("AGENT_REACT_TIMEOUT_SECONDS", raising=False)

    settings = AgentSettings(_env_file=None)

    assert settings.AGENT_REACT_ENABLED is False
    assert settings.AGENT_REACT_MAX_ITERATIONS == 2
    assert settings.AGENT_REACT_CONTROLLER_MODE == "rule"
    assert settings.AGENT_REACT_TIMEOUT_SECONDS == 5.0


def test_rule_react_controller_retrieves_when_source_backed_answer_lacks_sources(monkeypatch):
    from agent_service.graph.react_controller import decide_react_action

    monkeypatch.setenv("AGENT_REACT_ENABLED", "true")
    get_agent_settings.cache_clear()

    decision = decide_react_action(
        {
            "react_iteration": 0,
            "agents_to_run": ["property_search"],
            "warnings": ["final_response_missing_sources"],
            "evidence_by_id": {},
            "evidence_for_agent": {"property_search": []},
        }
    )
    get_agent_settings.cache_clear()

    assert decision.action == "retrieve_more"
    assert decision.agents == ["property_search"]
    assert decision.retrieval_domains == ["property"]
    assert decision.confidence == 1.0


def test_rule_react_controller_stops_at_iteration_budget(monkeypatch):
    from agent_service.graph.react_controller import decide_react_action

    monkeypatch.setenv("AGENT_REACT_ENABLED", "true")
    monkeypatch.setenv("AGENT_REACT_MAX_ITERATIONS", "1")
    get_agent_settings.cache_clear()

    decision = decide_react_action(
        {
            "react_iteration": 1,
            "agents_to_run": ["property_search"],
            "warnings": ["final_response_missing_sources"],
        }
    )
    get_agent_settings.cache_clear()

    assert decision.action == "finalize"
    assert "react_loop_exhausted" in decision.warnings


def test_react_decision_sanitizes_unknown_agents_domains_and_filters():
    from agent_service.graph.react_controller import ReactDecision

    decision = ReactDecision(
        action="retrieve_more",
        agents=["property_search", "unknown_agent", "property_search"],
        retrieval_domains=["property", "unknown_domain", "property"],
        filters={"district": "Quan 7", "locale": "vi-VN", "user_preferences": {}},
    )

    assert decision.agents == ["property_search"]
    assert decision.retrieval_domains == ["property"]
    assert decision.filters == {"district": "Quan 7"}
    warning_codes = {
        warning["code"]
        for warning in decision.warnings
        if isinstance(warning, dict)
    }
    assert "react_unknown_agents_dropped" in warning_codes
    assert "react_unknown_domains_dropped" in warning_codes


def test_rule_react_controller_retrieves_when_agent_answer_lacks_valid_evidence(monkeypatch):
    from agent_service.graph.react_controller import decide_react_action

    monkeypatch.setenv("AGENT_REACT_ENABLED", "true")
    get_agent_settings.cache_clear()

    decision = decide_react_action(
        {
            "react_iteration": 0,
            "agents_to_run": ["property_search"],
            "warnings": ["agent_answer_missing_valid_evidence"],
            "evidence_by_id": {},
            "evidence_for_agent": {"property_search": []},
            "agent_results": {
                "property_search": {
                    "evidence_ids_used": ["missing-id"],
                    "claims": [{"text": "unsupported", "evidence_ids": ["missing-id"]}],
                }
            },
            "query_understanding": {"filters": {"district": "Quan 7"}},
            "routing_filters": {"locale": "vi-VN"},
        }
    )
    get_agent_settings.cache_clear()

    assert decision.action == "retrieve_more"
    assert decision.agents == ["property_search"]
    assert decision.retrieval_domains == ["property"]
    assert decision.filters == {"district": "Quan 7"}


@pytest.mark.asyncio
async def test_graph_asks_clarification_without_running_retrieval_or_specialists(monkeypatch):
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "projects": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "news": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "legal": {"status": "ready", "parent_count": 1, "chunk_count": 1},
        }

    async def fake_route_request(state):
        return RouterDecision(
            intent="property_search",
            agents=["property_search"],
            confidence=0.9,
            needs_clarification=True,
            clarifying_question="Ban muon mua hay thue?",
            reason="missing listing_type",
        )

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)
    monkeypatch.setattr(nodes, "route_request", fake_route_request)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-react-clarify",
            session_id="session-1",
            message="Tim can ho Quan 7",
        )
    )

    step_names = [step["step_name"] for step in response.full_trace["steps"]]
    assert response.final_response == "Ban muon mua hay thue?"
    assert "clarification" in step_names
    assert "retrieval_planner" not in step_names
    assert "specialist_agents" not in step_names


@pytest.mark.asyncio
async def test_graph_react_retrieves_more_and_reruns_specialist(monkeypatch):
    monkeypatch.setenv("AGENT_REACT_ENABLED", "true")
    get_agent_settings.cache_clear()
    retrieval_calls = {"count": 0}

    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    async def fake_run_hybrid_tool(**kwargs):
        retrieval_calls["count"] += 1
        if retrieval_calls["count"] == 1:
            return []
        return [
            {
                "id": 1,
                "product_id": "p-react",
                "title": "Can ho ReAct Quan 7",
                "url": "https://example.test/react",
                "matched_chunk": {
                    "id": "chunk-react",
                    "text": "Can ho ReAct Quan 7",
                    "rerank_score": 0.91,
                },
            }
        ]

    async def fake_property_agent(**kwargs):
        evidence = kwargs["evidence"]
        if not evidence:
            return {
                "agent_name": "property_search",
                "status": "completed",
                "content": "Can ho ReAct co ve phu hop.",
                "evidence_ids_used": [],
                "warnings": [],
            }
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "Can ho ReAct Quan 7 co bang chung hop le.",
            "evidence_ids_used": [evidence[0]["evidence_id"]],
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)
    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_hybrid_tool)
    monkeypatch.setattr(nodes, "run_property_agent", fake_property_agent)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-react-loop",
            session_id="session-1",
            message="Tim can ho Quan 7",
        )
    )
    get_agent_settings.cache_clear()

    step_names = [step["step_name"] for step in response.full_trace["steps"]]
    assert step_names.count("specialist_agents") == 2
    assert "react_controller" in step_names
    assert "react_retrieval" in step_names
    assert retrieval_calls["count"] == 2
    assert response.sources
    assert "react_loop_exhausted" not in response.trace_summary.warnings


@pytest.mark.asyncio
async def test_graph_react_finalizes_with_warning_when_loop_budget_is_exhausted(monkeypatch):
    monkeypatch.setenv("AGENT_REACT_ENABLED", "true")
    monkeypatch.setenv("AGENT_REACT_MAX_ITERATIONS", "1")
    get_agent_settings.cache_clear()

    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    async def empty_run_hybrid_tool(**kwargs):
        return []

    async def unsupported_property_agent(**kwargs):
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "Can ho nay co ve phu hop nhung chua co nguon.",
            "evidence_ids_used": [],
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)
    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", empty_run_hybrid_tool)
    monkeypatch.setattr(nodes, "run_property_agent", unsupported_property_agent)

    response = await run_agent_graph(
        AgentChatRequest(
            request_id="req-react-exhausted",
            session_id="session-1",
            message="Tim can ho Quan 7",
        )
    )
    get_agent_settings.cache_clear()

    step_names = [step["step_name"] for step in response.full_trace["steps"]]
    assert step_names.count("react_controller") == 2
    assert "react_loop_exhausted" in response.trace_summary.warnings
    assert response.final_response
