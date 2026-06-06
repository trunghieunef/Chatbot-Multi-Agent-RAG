import pytest

from agent_service.contracts import AgentChatRequest, AgentSource, StructuredWarning
from agent_service.graph import nodes
from agent_service.graph.nodes import _strip_accents
from agent_service.graph.workflow import run_agent_graph


def test_strip_accents_handles_none():
    assert _strip_accents(None) == ""


@pytest.mark.asyncio
async def test_agent_graph_returns_trace_summary_without_llm_key(monkeypatch):
    request = AgentChatRequest(
        request_id="req-graph-1",
        message="Tim can ho Quan 7 duoi 5 ty",
        session_id="session-1",
        user_preferences={"preferred_district": {"value": "Quan 7"}},
    )

    response = await run_agent_graph(request)

    assert response.request_id == "req-graph-1"
    assert response.final_response
    assert "property_search" in response.agents_used
    assert response.trace_summary.intent == "property_search"
    assert response.full_trace["request_id"] == "req-graph-1"
    assert response.full_trace["steps"]
    assert response.readiness["listings"]["status"] == "unknown"
    assert all(
        step["status"] == "success" for step in response.full_trace["steps"]
    )
    assert isinstance(response.full_trace["agent_results"]["property_search"], dict)
    assert response.full_trace["agent_results"]["property_search"]["content"]


@pytest.mark.asyncio
async def test_agent_graph_runs_safety_validator_before_memory_proposals():
    request = AgentChatRequest(
        request_id="req-graph-safety",
        message="Tim can ho Quan 7 duoi 5 ty",
        session_id="session-1",
    )

    response = await run_agent_graph(request)

    step_names = [
        step["step_name"] for step in response.full_trace["steps"]
    ]
    assert "safety_validator" in step_names
    assert step_names.index("safety_validator") > step_names.index("synthesizer")
    assert step_names.index("safety_validator") < step_names.index("memory_proposals")


def test_safety_validator_flags_missing_sources_without_changing_answer_payload():
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    original_response = "Can ho A phu hop voi ngan sach va khu vuc Quan 7."
    suggested_actions = ["So sanh lua chon"]
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-node",
            message="Tim can ho Quan 7 duoi 5 ty",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "final_response": original_response,
        "sources": [],
        "suggested_actions": suggested_actions,
        "warnings": ["existing_warning", "existing_warning"],
        "trace_steps": [],
    }

    result = validator(state)

    assert result["final_response"] == original_response
    assert result["sources"] == []
    assert result["suggested_actions"] == suggested_actions
    assert result["warnings"] == [
        "existing_warning",
        "final_response_missing_sources",
    ]
    assert result["trace_steps"][-1]["step_name"] == "safety_validator"
    assert result["trace_steps"][-1]["output"]["warning_count"] == 2


def test_synthesizer_dedupes_structured_warnings_without_losing_objects():
    synthesizer = getattr(nodes, "synthesizer_node", None)
    assert callable(synthesizer)
    warning = StructuredWarning(
        code="source_not_ready",
        domain="legal",
        message="Legal source is not ready.",
    )
    state = {
        "request": AgentChatRequest(
            request_id="req-synth-structured-warning",
            message="Can kiem tra gi truoc khi dat coc?",
            session_id="session-1",
        ),
        "agents_to_run": ["legal_advisor"],
        "agent_results": {
            "legal_advisor": {
                "content": "Chua co can cu phap ly de ket luan.",
                "warnings": [warning],
                "sources": [],
            }
        },
        "warnings": [warning],
        "trace_steps": [],
    }

    result = synthesizer(state)

    assert result["warnings"] == [warning]


def test_safety_validator_preserves_structured_warnings_when_adding_warnings():
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    existing_warning = StructuredWarning(
        code="source_not_ready",
        domain="property",
        message="Property source is not ready.",
    )
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-structured-warning",
            message="Tim can ho Quan 7 duoi 5 ty",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "final_response": "Can ho A phu hop voi ngan sach va khu vuc Quan 7.",
        "sources": [],
        "suggested_actions": [],
        "warnings": [existing_warning],
        "trace_steps": [],
    }

    result = validator(state)

    assert result["warnings"][0] == existing_warning
    assert result["warnings"][1] == "final_response_missing_sources"


def test_safety_validator_flags_legal_answer_without_disclaimer():
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    original_response = "Nguoi mua can kiem tra so do truoc khi dat coc."
    source = AgentSource(type="legal_article", id=1, title="Legal checklist")
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-legal",
            message="Can kiem tra gi truoc khi dat coc?",
            session_id="session-1",
        ),
        "agents_to_run": ["legal_advisor"],
        "final_response": original_response,
        "sources": [source],
        "suggested_actions": [],
        "warnings": [],
        "trace_steps": [],
    }

    result = validator(state)

    assert result["final_response"] == original_response
    assert result["sources"] == [source]
    assert result["warnings"] == ["legal_disclaimer_missing"]


def test_safety_validator_flags_investment_answer_without_financial_disclaimer():
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    original_response = "Can ho nay co dong tien cho thue kha on dinh."
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-investment",
            message="Danh gia dau tu can ho nay",
            session_id="session-1",
        ),
        "agents_to_run": ["investment_advisor"],
        "final_response": original_response,
        "sources": [],
        "suggested_actions": [],
        "warnings": [],
        "trace_steps": [],
    }

    result = validator(state)

    assert result["final_response"] == original_response
    assert result["warnings"] == ["financial_disclaimer_missing"]


@pytest.mark.asyncio
async def test_agent_graph_routes_legal_question_without_llm_key():
    request = AgentChatRequest(
        request_id="req-graph-2",
        message="Tu van phap ly sang ten so do",
        session_id="session-1",
    )

    response = await run_agent_graph(request)

    assert response.agents_used == ["legal_advisor"]
    assert response.trace_summary.intent == "legal_advice"


@pytest.mark.asyncio
async def test_agent_graph_does_not_route_property_from_keyword_substring():
    request = AgentChatRequest(
        request_id="req-news-1",
        message="Cap nhat tin tuc thi truong",
        session_id="session-1",
    )

    response = await run_agent_graph(request)

    assert "property_search" not in response.agents_used
    assert response.agents_used == ["market_analysis", "news_agent"]
    assert response.trace_summary.intent == "mixed"


@pytest.mark.asyncio
async def test_retrieval_planner_node_uses_single_node_with_testable_functions(monkeypatch):
    request = AgentChatRequest(
        request_id="req-planner-node",
        message="Tim can ho Quan 7",
        session_id="session-1",
    )
    state = {
        "request": request,
        "agents_to_run": ["property_search"],
        "readiness": {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
        },
        "trace_steps": [],
        "warnings": [],
    }
    called = {}

    def fake_build(input_state):
        called["build"] = input_state["request"].request_id
        return []

    async def fake_execute(plan, input_state):
        called["execute"] = len(plan)
        return {
            "retrieval_plan": [],
            "retrieval_results": {},
            "evidence_by_id": {},
            "evidence_for_agent": {"property_search": []},
            "retrieval_events": [],
            "warnings": [],
        }

    monkeypatch.setattr(nodes, "build_retrieval_plan", fake_build)
    monkeypatch.setattr(nodes, "execute_retrieval_plan", fake_execute)

    result = await nodes.retrieval_planner_node(state)

    assert called == {"build": "req-planner-node", "execute": 0}
    assert result["evidence_for_agent"] == {"property_search": []}
    assert result["trace_steps"][-1]["step_name"] == "retrieval_planner"
