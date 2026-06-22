from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentThought,
    StructuredWarning,
)
from agent_service.graph.blackboard import read_blackboard


def _warning(code: str, message: str) -> StructuredWarning:
    return StructuredWarning(code=code, message=message)


class BaseAgent(ABC):
    """Abstract base for all autonomous specialist agents.

    Implements the ReAct (Reasoning + Acting) loop:
        think → act → observe → (repeat or stop)

    Subclasses implement:
      - think():   Decide what to do next
      - act():     Execute the decided action
      - observe(): Determine if the loop should stop
      - build_result(): Produce the final AgentResult
    """

    def __init__(
        self,
        *,
        agent_name: str,
        max_iterations: int = 3,
    ):
        self.agent_name = agent_name
        self.max_iterations = max_iterations
        self._tool_registry: Any = None

    # ── Subclass interface ──────────────────────────────────────

    @abstractmethod
    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        """Decide the next action.

        Args:
            context: Full agent context (query, filters, preferences, etc.)
            iteration: Current loop iteration (0-indexed).
            previous_actions: All actions taken so far in this run.
            blackboard_entries: Latest entries from the shared blackboard.

        Returns:
            AgentThought with action, tool_name, tool_params, etc.
        """
        ...

    @abstractmethod
    async def act(
        self,
        thought: AgentThought,
        context: AgentContext,
    ) -> AgentAction:
        """Execute the action decided by think().

        For call_tool actions, this should call self.call_tool().
        For final_answer, this should return immediately.
        """
        ...

    @abstractmethod
    async def observe(
        self,
        thought: AgentThought,
        action: AgentAction,
        context: AgentContext,
    ) -> bool:
        """Determine if the ReAct loop should stop.

        Returns:
            True if the agent has enough information to answer.
        """
        ...

    @abstractmethod
    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        """Build the final AgentResult from the completed loop."""
        ...

    # ── Shared infrastructure ────────────────────────────────────

    async def call_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        """Call a tool via the ToolRegistry.

        Subclasses should use this rather than calling tools directly.
        The ToolRegistry is injected at run time via run().
        """
        if self._tool_registry is None:
            raise RuntimeError(
                "ToolRegistry not set. Call agent.run() which injects it."
            )
        return await self._tool_registry.call(
            tool_name=tool_name,
            agent_name=self.agent_name,
            **tool_params,
        )

    def _read_blackboard(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return read_blackboard(state, min_confidence="low", max_entries=20)

    # ── ReAct loop ───────────────────────────────────────────────

    async def run(
        self,
        context: AgentContext,
        state: dict[str, Any],
        *,
        tool_registry: Any | None = None,
        timeout_seconds: float = 30.0,
    ) -> AgentResult:
        """Execute the full ReAct loop.

        Args:
            context: AgentContext with query, filters, preferences.
            state: Full graph state (for blackboard access).
            tool_registry: ToolRegistry instance for tool calling.
            timeout_seconds: Max time for the entire agent run.

        Returns:
            AgentResult with content, sources, evidence_ids, etc.
        """
        self._tool_registry = tool_registry
        thoughts: list[AgentThought] = []
        actions: list[AgentAction] = []
        started = time.perf_counter()

        for iteration in range(self.max_iterations):
            elapsed = time.perf_counter() - started
            if elapsed > timeout_seconds:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content="Agent timed out before completing analysis.",
                    warnings=[_warning("agent_timeout", f"Timed out after {elapsed:.1f}s")],
                    iterations=iteration,
                )

            try:
                blackboard_entries = self._read_blackboard(state)
                thought = await self.think(
                    context, iteration, actions, blackboard_entries
                )
                thoughts.append(thought)
            except Exception as exc:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content=f"Agent failed during think: {exc}",
                    warnings=[_warning("think_error", str(exc))],
                    iterations=iteration,
                )

            if thought.action == "final_answer":
                action = AgentAction(
                    iteration=iteration,
                    action_type="final_answer",
                    status="success",
                )
                actions.append(action)
                return self.build_result(context, thoughts, actions)

            if thought.action == "ask_clarification":
                return AgentResult(
                    agent_name=self.agent_name,
                    status="partial",
                    content=thought.clarifying_question
                    or "Could you provide more details?",
                    iterations=iteration,
                )

            try:
                action = await self.act(thought, context)
                actions.append(action)
            except Exception as exc:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content=f"Agent failed during act: {exc}",
                    warnings=[_warning("act_error", str(exc))],
                    iterations=iteration,
                )

            try:
                done = await self.observe(thought, action, context)
                if done:
                    return self.build_result(context, thoughts, actions)
            except Exception as exc:
                return AgentResult(
                    agent_name=self.agent_name,
                    status="failed",
                    content=f"Agent failed during observe: {exc}",
                    warnings=[_warning("observe_error", str(exc))],
                    iterations=iteration,
                )

        # Max iterations reached
        return self.build_result(context, thoughts, actions)
