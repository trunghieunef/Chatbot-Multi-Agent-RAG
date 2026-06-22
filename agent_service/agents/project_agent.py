from __future__ import annotations

from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.contracts import (
    AgentAction,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
)


class ProjectAgent(BaseAgent):
    """Autonomous project evaluation agent.

    Searches for real estate project information and evaluates
    developer credibility, progress, and legal status.

    Flow:
      1. think: Need project data → call search_projects
      2. final_answer: Summarize project info with caveats
    """

    def __init__(self, max_iterations: int = 2, use_llm: bool = False):
        super().__init__(agent_name="project_agent", max_iterations=max_iterations, use_llm=use_llm)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_projects = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_projects:
            return AgentThought(
                iteration=iteration,
                reasoning="Need to search for project information.",
                action="call_tool",
                tool_name="search_projects",
                tool_params={
                    "query": context.normalized_query,
                    "filters": context.routing_filters,
                    "top_k": 15,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Project data gathered. Ready to present.",
            action="final_answer",
            confidence=0.9,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            return AgentAction(
                iteration=thought.iteration,
                action_type="final_answer",
                status="success",
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=result.get("evidence_ids", []),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except Exception as exc:
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="error",
                error_message=str(exc),
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )

    async def observe(
        self, thought: AgentThought, action: AgentAction, context: AgentContext
    ) -> bool:
        return thought.action == "final_answer"

    def build_result(
        self,
        context: AgentContext,
        thoughts: list[AgentThought],
        actions: list[AgentAction],
    ) -> AgentResult:
        all_projects: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                all_projects.extend(
                    item for item in results if isinstance(item, dict) and item.get("title")
                )
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_projects:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content="Chưa tìm thấy thông tin dự án phù hợp.",
                iterations=len(thoughts),
            )

        lines = ["🏗️ **Thông tin dự án bất động sản:**\n"]
        for i, project in enumerate(all_projects[:5], 1):
            title = project.get("title", "Dự án")
            developer = project.get("developer", "Chưa rõ chủ đầu tư")
            location = project.get("location", "")
            lines.append(f"**{i}. {title}**")
            lines.append(f"   🏢 Chủ đầu tư: {developer}")
            if location:
                lines.append(f"   📍 {location}")
            lines.append("")

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=[],
            confidence="medium",
            iterations=len(thoughts),
        )
