import pytest

from agent_service.contracts import (
    AgentChatRequest,
    AgentSource,
    Evidence,
    MatchedChunk,
    StructuredWarning,
)
from agent_service.graph import nodes
from agent_service.graph.nodes import _strip_accents
from agent_service.graph.workflow import run_agent_graph


def test_agent_llm_flags_default_to_deterministic(monkeypatch):
    from agent_service.config import AgentSettings

    monkeypatch.delenv("AGENT_ROUTER_MODE", raising=False)
    monkeypatch.delenv("AGENT_QUERY_REWRITE_ENABLED", raising=False)
    monkeypatch.delenv("AGENT_SPECIALIST_LLM_ENABLED", raising=False)

    settings = AgentSettings(_env_file=None)

    assert settings.AGENT_ROUTER_MODE == "rule"
    assert settings.AGENT_QUERY_REWRITE_ENABLED is False
    assert settings.AGENT_MEMORY_FILTERS_ENABLED is False
    assert settings.AGENT_SPECIALIST_LLM_ENABLED is False


def test_live_llm_requires_explicit_gemini_model(monkeypatch, tmp_path):
    from agent_service.config import AgentSettings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "key")
    monkeypatch.setenv("AGENT_ROUTER_MODE", "llm")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    with pytest.raises(ValueError, match="GEMINI_MODEL"):
        AgentSettings()


def test_strip_accents_handles_none():
    assert _strip_accents(None) == ""


@pytest.mark.asyncio
async def test_agent_graph_returns_trace_summary_without_llm_key(monkeypatch):
    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
            "projects": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
            "legal": {"status": "unknown", "parent_count": 0, "chunk_count": 0},
        }

    monkeypatch.setattr(nodes, "build_readiness_snapshot", fake_readiness_snapshot)

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


def test_safety_validator_accepts_no_listing_evidence_warning():
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-listing-warning",
            message="Tim can ho Quan 7",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "final_response": "Chua co bang chung listing phu hop.",
        "sources": [],
        "suggested_actions": [],
        "warnings": [
            StructuredWarning(
                code="no_listing_evidence",
                domain="property",
                message="No listing evidence was found.",
            )
        ],
        "trace_steps": [],
    }

    result = validator(state)

    codes = [
        warning.code if hasattr(warning, "code") else warning
        for warning in result["warnings"]
    ]
    assert codes == ["no_listing_evidence"]


@pytest.mark.parametrize(
    ("agent", "warning"),
    [
        (
            "property_search",
            StructuredWarning(
                code="listing_source_not_ready",
                domain="property",
                message="Listing source is not ready.",
            ),
        ),
        (
            "legal_advisor",
            StructuredWarning(
                code="insufficient_legal_evidence",
                domain="legal",
                message="Legal evidence is missing.",
            ),
        ),
    ],
)
def test_safety_validator_accepts_intentional_no_source_warnings(agent, warning):
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-no-source-warning",
            message="Can kiem tra nguon",
            session_id="session-1",
        ),
        "agents_to_run": [agent],
        "final_response": "Chua co bang chung du de ket luan.",
        "sources": [],
        "suggested_actions": [],
        "warnings": [warning],
        "trace_steps": [],
    }

    result = validator(state)

    codes = [
        item.code if hasattr(item, "code") else item
        for item in result["warnings"]
    ]
    assert warning.code in codes
    assert "final_response_missing_sources" not in codes


@pytest.mark.asyncio
async def test_synthesizer_exposes_only_valid_used_evidence():
    valid_source = AgentSource(
        type="listing",
        domain="property",
        id="listing:p-1",
        title="Can ho A",
        metadata={"source_identity": "listing:p-1"},
    )
    unused_source = AgentSource(
        type="listing",
        domain="property",
        id="listing:p-2",
        title="Can ho B",
        metadata={"source_identity": "listing:p-2"},
    )
    evidence_by_id = {
        "ev_valid": Evidence(
            evidence_id="ev_valid",
            retrieval_task_id="search_property_1",
            domain="property",
            source_type="listing",
            source_identity="listing:p-1",
            record={},
            facts={"title": "Can ho A"},
            source=valid_source,
            matched_chunks=[MatchedChunk(text="chunk A")],
            retrieved_for=["property_search"],
            assigned_to=["property_search"],
        ),
        "ev_unused": Evidence(
            evidence_id="ev_unused",
            retrieval_task_id="search_property_1",
            domain="property",
            source_type="listing",
            source_identity="listing:p-2",
            record={},
            facts={"title": "Can ho B"},
            source=unused_source,
            retrieved_for=["property_search"],
            assigned_to=["property_search"],
        ),
    }
    state = {
        "request": AgentChatRequest(
            request_id="req-synth-valid",
            message="Tim can ho",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "evidence_by_id": evidence_by_id,
        "evidence_for_agent": {"property_search": ["ev_valid", "ev_unused"]},
        "agent_results": {
            "property_search": {
                "content": "Can ho A phu hop.",
                "evidence_ids_used": ["ev_valid", "ev_missing"],
                "warnings": [],
                "sources": [],
            }
        },
        "trace_steps": [],
        "warnings": [],
        "force_deterministic": True,
    }

    result = await nodes.synthesizer_node(state)

    assert [source.id for source in result["sources"]] == ["listing:p-1"]
    warning_codes = [
        warning.code if hasattr(warning, "code") else warning.get("code")
        for warning in result["warnings"]
    ]
    assert "invalid_evidence_reference" in warning_codes
    assert result["trace_steps"][-1]["output"]["used_evidence_ids"] == ["ev_valid"]


@pytest.mark.asyncio
async def test_synthesizer_rejects_unassigned_evidence_id():
    source = AgentSource(type="article", domain="legal", id="article:1")
    evidence = Evidence(
        evidence_id="ev_legal",
        retrieval_task_id="search_legal_1",
        domain="legal",
        source_type="article",
        source_identity="article:1",
        record={},
        facts={},
        source=source,
        assigned_to=["legal_advisor"],
    )
    state = {
        "request": AgentChatRequest(
            request_id="req-synth-unassigned",
            message="Tim can ho",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "evidence_by_id": {"ev_legal": evidence},
        "evidence_for_agent": {"property_search": []},
        "agent_results": {
            "property_search": {
                "content": "Bad citation.",
                "evidence_ids_used": ["ev_legal"],
                "warnings": [],
                "sources": [],
            }
        },
        "trace_steps": [],
        "warnings": [],
        "force_deterministic": True,
    }

    result = await nodes.synthesizer_node(state)

    assert result["sources"] == []
    assert any(
        (warning.code if hasattr(warning, "code") else warning.get("code"))
        == "invalid_evidence_reference"
        for warning in result["warnings"]
    )


@pytest.mark.asyncio
async def test_synthesizer_dedupes_structured_warnings_without_losing_objects():
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
        "force_deterministic": True,
    }

    result = await synthesizer(state)

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


def test_safety_validator_replaces_unsupported_claim_content():
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    original_response = "Can ho nay chac chan tang gia manh trong 12 thang toi."
    fallback_response = "Chua co du bang chung hop le de ket luan ve gia."
    evidence = Evidence(
        evidence_id="ev_valid",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p-1",
        record={},
        facts={"title": "Can ho A"},
        source=AgentSource(type="listing", domain="property", id="listing:p-1"),
        assigned_to=["property_search"],
    )
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-claims",
            message="Can ho nay co tang gia khong?",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "agent_results": {
            "property_search": {
                "content": original_response,
                "fallback_content": fallback_response,
                "claims": [
                    {
                        "type": "fact",
                        "text": original_response,
                        "evidence_ids": ["ev_missing"],
                    },
                    {
                        "type": "fact",
                        "text": "Can ho A co trong bang chung.",
                        "evidence_ids": ["ev_valid"],
                    },
                    {
                        "type": "fact",
                        "text": "Nguon listing duoc dung de tham khao.",
                        "evidence_ids": ["ev_valid"],
                    },
                    {
                        "type": "fact",
                        "text": "Can ho A nam trong tap bang chung.",
                        "evidence_ids": ["ev_valid"],
                    },
                    {
                        "type": "disclaimer",
                        "text": "Can tu tham dinh them.",
                    },
                ],
                "warnings": [],
            }
        },
        "evidence_by_id": {"ev_valid": evidence},
        "evidence_for_agent": {"property_search": ["ev_valid"]},
        "final_response": original_response,
        "sources": [evidence.source],
        "suggested_actions": [],
        "warnings": [],
        "trace_steps": [],
    }

    result = validator(state)

    assert result["final_response"] == fallback_response
    assert "agent_answer_missing_valid_evidence" in result["warnings"]
    assert result["trace_steps"][-1]["output"]["grounding_fallback_agents"] == [
        "property_search"
    ]


def test_safety_validator_rejects_partially_fake_claim_evidence_ids():
    validator = getattr(nodes, "safety_validator_node", None)
    assert callable(validator)
    original_response = "Can ho A co du bang chung va them nguon khong ton tai."
    fallback_response = "Chua co du bang chung hop le de ket luan."
    evidence = Evidence(
        evidence_id="ev_valid",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p-1",
        record={},
        facts={"title": "Can ho A"},
        source=AgentSource(type="listing", domain="property", id="listing:p-1"),
        assigned_to=["property_search"],
    )
    state = {
        "request": AgentChatRequest(
            request_id="req-safety-partial-fake-claim",
            message="Can ho nay co on khong?",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "agent_results": {
            "property_search": {
                "content": original_response,
                "fallback_content": fallback_response,
                "claims": [
                    {
                        "type": "fact",
                        "text": original_response,
                        "evidence_ids": ["ev_valid", "ev_fake"],
                    }
                ],
                "warnings": [],
            }
        },
        "evidence_by_id": {"ev_valid": evidence},
        "evidence_for_agent": {"property_search": ["ev_valid"]},
        "final_response": original_response,
        "sources": [evidence.source],
        "suggested_actions": [],
        "warnings": [],
        "trace_steps": [],
    }

    result = validator(state)

    assert result["final_response"] == fallback_response
    assert "agent_answer_missing_valid_evidence" in result["warnings"]


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


@pytest.mark.asyncio
async def test_specialist_agents_node_resolves_assigned_evidence(monkeypatch):
    seen = {}

    async def fake_property_agent(**kwargs):
        seen["evidence"] = kwargs["evidence"]
        return {
            "agent_name": "property_search",
            "status": "completed",
            "content": "ok",
            "evidence_ids_used": ["ev_property_1"],
            "warnings": [],
            "sources": [],
        }

    monkeypatch.setattr(nodes, "run_property_agent", fake_property_agent)
    evidence = Evidence(
        evidence_id="ev_property_1",
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p-1",
        record={},
        facts={"title": "Can ho Quan 7"},
        source=AgentSource(type="listing", domain="property", id="listing:p-1"),
        assigned_to=["property_search"],
    )
    state = {
        "request": AgentChatRequest(
            request_id="req-specialist-evidence",
            message="Tim can ho Quan 7",
            session_id="session-1",
        ),
        "agents_to_run": ["property_search"],
        "evidence_by_id": {"ev_property_1": evidence},
        "evidence_for_agent": {"property_search": ["ev_property_1"]},
        "readiness": {},
        "trace_steps": [],
    }

    result = await nodes.specialist_agents_node(state)

    assert seen["evidence"][0]["evidence_id"] == "ev_property_1"
    assert result["agent_results"]["property_search"]["evidence_ids_used"] == [
        "ev_property_1"
    ]


@pytest.mark.asyncio
async def test_mixed_property_legal_investment_query_uses_shared_evidence(monkeypatch):
    calls = []

    async def fake_run_hybrid_tool(**kwargs):
        calls.append(kwargs["tool_name"])
        if kwargs["parent_type"] == "listing":
            return [
                {
                    "id": 1,
                    "product_id": "p-q7",
                    "title": "Can ho 2PN Quan 7",
                    "price": 4.8,
                    "price_text": "4.8 ty",
                    "area": 75,
                    "area_text": "75 m2",
                    "district": "Quan 7",
                    "city": "Ho Chi Minh",
                    "legal_status": "So hong",
                    "url": "https://example.test/listing/p-q7",
                    "matched_chunk": {
                        "id": 10,
                        "chunk_type": "overview",
                        "text": "Can ho 2PN Quan 7 duoi 5 ty",
                        "distance": 0.2,
                        "rerank_score": 0.93,
                    },
                }
            ]
        if kwargs["parent_type"] == "article":
            assert kwargs["filters"] == {"category": "legal"}
            return [
                {
                    "id": 7,
                    "title": "Dieu kien chuyen nhuong can ho",
                    "category": "legal",
                    "url": "legal://transfer",
                    "citation": {"doc_slug": "luat-nha-o", "dieu_number": "32"},
                    "matched_chunk": {
                        "id": 70,
                        "chunk_type": "legal_section",
                        "text": "Quy dinh ve dieu kien chuyen nhuong.",
                        "distance": 0.25,
                        "rerank_score": 0.88,
                    },
                }
            ]
        return []

    async def fake_readiness_snapshot():
        return {
            "listings": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "legal": {"status": "ready", "parent_count": 1, "chunk_count": 1},
            "projects": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
            "news": {"status": "not_ready", "parent_count": 0, "chunk_count": 0},
        }

    monkeypatch.setattr(
        "agent_service.graph.retrieval_planner._run_hybrid_tool",
        fake_run_hybrid_tool,
    )
    monkeypatch.setattr(
        nodes,
        "build_readiness_snapshot",
        fake_readiness_snapshot,
    )

    request = AgentChatRequest(
        request_id="req-mixed-acceptance",
        message=(
            "Tim can ho Quan 7 duoi 5 ty, phap ly on va co tiem nang dau tu khong?"
        ),
        session_id="session-1",
    )

    response = await run_agent_graph(request)

    assert set(response.agents_used) >= {
        "property_search",
        "legal_advisor",
        "investment_advisor",
    }
    assert calls.count("search_listings") == 1
    assert calls.count("search_articles") == 1
    trace = response.full_trace
    property_ids = trace["evidence_for_agent"]["property_search"]
    investment_ids = trace["evidence_for_agent"]["investment_advisor"]
    assert property_ids[0] in investment_ids
    warning_codes = [
        warning.code
        if hasattr(warning, "code")
        else warning["code"]
        if isinstance(warning, dict)
        else warning
        for warning in response.trace_summary.warnings
    ]
    assert "investment_market_data_missing" in warning_codes
    assert "du dieu kien phap ly" not in response.final_response.lower()
    source_ids = [source.id for source in response.sources]
    assert "listing:p-q7" in source_ids
    assert "article:legal://transfer" in source_ids
    used_ids = set()
    for result in trace["agent_results"].values():
        used_ids.update(result.get("evidence_ids_used", []))
    source_identities = {
        trace["evidence"][evidence_id]["source_identity"]
        for evidence_id in used_ids
        if evidence_id in trace["evidence"]
    }
    assert set(source_ids).issubset(source_identities)



