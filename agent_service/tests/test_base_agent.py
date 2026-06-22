import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentContext,
    AgentResult,
    AgentThought,
    AgentAction,
    ToolDef,
)
from agent_service.graph.blackboard import BlackboardEntry
from agent_service.graph.state import AgentGraphState


class CountingAgent(BaseAgent):
    """Test agent that counts iterations then answers."""

    def __init__(self, max_iterations: int = 3):
        super().__init__(agent_name="counting_agent", max_iterations=max_iterations)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict],
    ) -> AgentThought:
        if iteration >= self.max_iterations:
            return AgentThought(
                iteration=iteration,
                reasoning="Max iterations reached, must answer.",
                action="final_answer",
                confidence=0.5,
            )
        return AgentThought(
            iteration=iteration,
            reasoning=f"Iteration {iteration}, need more data.",
            action="call_tool",
            tool_name="fake_search",
            tool_params={"query": context.query, "iter": iteration},
            confidence=0.7,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
                tool_result={"answer": f"Done at iteration {thought.iteration}"},
            )
        return AgentAction(
            iteration=thought.iteration,
            action_type="call_tool",
            status="success",
            tool_result={"results": [{"id": 1, "title": "Test listing"}]},
            evidence_ids=["ev_001"],
        )

    async def observe(
        self,
        thought: AgentThought,
        action: AgentAction,
        context: AgentContext,
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="Counting complete.",
            evidence_ids_used=["ev_001"],
            iterations=len(thoughts),
        )


@pytest.fixture
def agent_context():
    return AgentContext(
        agent_name="counting_agent",
        query="test query",
        normalized_query="test query",
    )


@pytest.mark.asyncio
async def test_base_agent_runs_react_loop(agent_context):
    agent = CountingAgent(max_iterations=2)
    result = await agent.run(agent_context, {})

    assert result.agent_name == "counting_agent"
    assert result.status == "completed"
    assert result.iterations == 2


@pytest.mark.asyncio
async def test_base_agent_respects_max_iterations(agent_context):
    agent = CountingAgent(max_iterations=1)
    result = await agent.run(agent_context, {})

    assert result.iterations == 1
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_base_agent_enforces_timeout(agent_context):
    """Agent that thinks forever should be stopped by timeout."""
    class SlowAgent(CountingAgent):
        async def think(self, context, iteration, previous_actions, blackboard_entries):
            await asyncio.sleep(10.0)
            return await super().think(context, iteration, previous_actions, blackboard_entries)

    agent = SlowAgent(max_iterations=5)
    result = await agent.run(agent_context, {}, timeout_seconds=0.1)

    assert result.status == "failed"
    assert any("timeout" in str(w).lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_base_agent_handles_think_exception(agent_context):
    class ErrorAgent(CountingAgent):
        async def think(self, context, iteration, previous_actions, blackboard_entries):
            raise RuntimeError("Think failed")

    agent = ErrorAgent(max_iterations=3)
    result = await agent.run(agent_context, {})

    assert result.status == "failed"
    assert any("Think failed" in str(w) for w in result.warnings)
