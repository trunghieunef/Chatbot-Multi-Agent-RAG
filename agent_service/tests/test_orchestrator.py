import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_service.agents.orchestrator import OrchestratorAgent
from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentChatRequest,
    AgentChatResponse,
    AgentContext,
    AgentResult,
    AgentThought,
    ConversationContextItem,
)
import agent_service.agents.orchestrator as orchestrator_module
from agent_service.graph.router import RouterDecision
from agent_service.tools.registry import ToolRegistry, ToolDef


@pytest.fixture
def chat_request():
    return AgentChatRequest(
        request_id="test-001",
        message="Tìm căn hộ Quận 7 dưới 3 tỷ",
        session_id="sess-001",
    )


@pytest.fixture
def tool_registry():
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="search_listings",
        description="Search listings",
        allowed_for=["property_search", "investment_advisor"],
    ))

    async def fake_search(*, query, filters=None, top_k=20, rerank_to=5):
        return {
            "status": "success",
            "results": [
                {"id": "L001", "title": "Căn hộ Quận 7", "price_text": "2.5 tỷ",
                 "area_text": "70m²", "district": "Quận 7", "city": "Hồ Chí Minh"},
            ],
            "evidence_ids": ["ev_L001"],
        }

    reg.bind("search_listings", fake_search)
    return reg


@pytest.mark.asyncio
async def test_orchestrator_routes_and_dispatches(chat_request, tool_registry):
    orchestrator = OrchestratorAgent(tool_registry=tool_registry)
    response = await orchestrator.run(chat_request)

    assert isinstance(response, AgentChatResponse)
    assert response.request_id == "test-001"
    assert len(response.agents_used) >= 1
    assert "property_search" in response.agents_used
    assert len(response.final_response) > 0


@pytest.mark.asyncio
async def test_orchestrator_handles_empty_query():
    req = AgentChatRequest(
        request_id="test-002",
        message=" ",
        session_id="sess-002",
    )
    orchestrator = OrchestratorAgent(tool_registry=ToolRegistry())
    response = await orchestrator.run(req)

    assert response.request_id == "test-002"
    assert len(response.final_response) > 0


class BlackboardWriterAgent(BaseAgent):
    def __init__(self, max_iterations: int = 3, use_llm: bool = False):
        super().__init__(
            agent_name="property_search",
            max_iterations=max_iterations,
            use_llm=use_llm,
        )

    async def think(self, context, iteration, previous_actions, blackboard_entries):
        if previous_actions:
            return AgentThought(
                iteration=iteration,
                reasoning="Writer has already published data.",
                action="final_answer",
                confidence=0.9,
            )
        return AgentThought(
            iteration=iteration,
            reasoning="Publish listing evidence first.",
            action="call_tool",
            tool_name="publish_listing",
            tool_params={},
            confidence=0.9,
        )

    async def act(self, thought, context):
        result = await self.call_tool(thought.tool_name, thought.tool_params, context)
        return AgentAction(
            iteration=thought.iteration,
            action_type="call_tool",
            status="success",
            tool_result=result,
            evidence_ids=result.get("evidence_ids", []),
        )

    async def observe(self, thought, action, context):
        return False

    def build_result(self, context, thoughts, actions):
        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="Writer final answer",
            evidence_ids_used=["ev_listing_1"],
            confidence="high",
            iterations=len(thoughts),
        )


class BlackboardReaderAgent(BaseAgent):
    def __init__(self, max_iterations: int = 3, use_llm: bool = False):
        super().__init__(
            agent_name="investment_advisor",
            max_iterations=max_iterations,
            use_llm=use_llm,
        )

    async def think(self, context, iteration, previous_actions, blackboard_entries):
        writer_entries = [
            entry for entry in blackboard_entries
            if entry.get("author") == "property_search"
        ]
        if writer_entries:
            return AgentThought(
                iteration=iteration,
                reasoning="Reader found writer evidence on blackboard.",
                action="final_answer",
                confidence=0.9,
            )
        return AgentThought(
            iteration=iteration,
            reasoning="Reader waits for writer evidence.",
            action="call_tool",
            tool_name="wait_for_blackboard",
            tool_params={},
            confidence=0.2,
        )

    async def act(self, thought, context):
        result = await self.call_tool(thought.tool_name, thought.tool_params, context)
        return AgentAction(
            iteration=thought.iteration,
            action_type="call_tool",
            status="success",
            tool_result=result,
            evidence_ids=result.get("evidence_ids", []),
        )

    async def observe(self, thought, action, context):
        return False

    def build_result(self, context, thoughts, actions):
        saw_writer = any(
            thought.action == "final_answer"
            and "found writer evidence" in thought.reasoning
            for thought in thoughts
        )
        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content=(
                "Reader used property_search blackboard evidence"
                if saw_writer
                else "Reader did not see property_search evidence"
            ),
            confidence="medium",
            iterations=len(thoughts),
        )


@pytest.mark.asyncio
async def test_orchestrator_rounds_share_live_blackboard(monkeypatch):
    async def fake_route_request(state):
        return RouterDecision(
            intent="mixed",
            agents=["property_search", "investment_advisor"],
            confidence=1.0,
            filters={},
            reason="test",
        )

    registry = ToolRegistry()
    registry.register(
        ToolDef(
            name="publish_listing",
            allowed_for=["property_search"],
        )
    )
    registry.register(
        ToolDef(
            name="wait_for_blackboard",
            allowed_for=["investment_advisor"],
        )
    )

    async def publish_listing():
        return {
            "status": "success",
            "results": [{"id": "L001", "title": "Listing from writer"}],
            "evidence_ids": ["ev_listing_1"],
        }

    async def wait_for_blackboard():
        return {"status": "waiting", "results": [], "evidence_ids": []}

    registry.bind("publish_listing", publish_listing)
    registry.bind("wait_for_blackboard", wait_for_blackboard)

    monkeypatch.setattr(orchestrator_module, "route_request", fake_route_request)
    monkeypatch.setitem(
        orchestrator_module.AGENT_CLASSES,
        "property_search",
        BlackboardWriterAgent,
    )
    monkeypatch.setitem(
        orchestrator_module.AGENT_CLASSES,
        "investment_advisor",
        BlackboardReaderAgent,
    )

    response = await OrchestratorAgent(
        tool_registry=registry,
        max_agent_iterations=3,
    ).run(
        AgentChatRequest(
            request_id="test-round-blackboard",
            message="Evaluate this property",
            session_id="sess-round",
        )
    )

    assert "Reader used property_search blackboard evidence" in response.final_response
    assert response.full_trace["orchestration_mode"] == "round_based"
    assert response.full_trace["round_count"] >= 2
    assert any(
        entry["author"] == "property_search"
        for entry in response.full_trace["blackboard"]["entries"]
    )


class FakeSynthesizerClient:
    async def generate_text_with_usage(self, prompt, timeout_seconds=None):
        class Result:
            text = "Synthesized grounded answer"
            skipped_reason = None
            error_message = None

        return Result()


@pytest.mark.asyncio
async def test_orchestrator_uses_llm_synthesizer_when_available(
    chat_request,
    tool_registry,
    monkeypatch,
):
    async def fake_route_request(state):
        return RouterDecision(
            intent="property_search",
            agents=["property_search"],
            confidence=1.0,
            filters={},
            reason="test",
        )

    monkeypatch.setattr(orchestrator_module, "route_request", fake_route_request)
    orchestrator = OrchestratorAgent(tool_registry=tool_registry)
    orchestrator._llm_client = FakeSynthesizerClient()
    orchestrator.use_llm = True

    response = await orchestrator.run(chat_request)

    assert response.final_response == "Synthesized grounded answer"
    assert response.full_trace["synthesizer_mode"] == "llm"
