from __future__ import annotations

import asyncio
import time
from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.agents.property_search_agent import PropertySearchAgent
from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent
from agent_service.agents.investment_advisor_agent import InvestmentAdvisorAgent
from agent_service.agents.project_agent import ProjectAgent
from agent_service.agents.news_agent import NewsAgent
from agent_service.config import get_agent_settings
from agent_service.contracts import (
    AgentChatRequest,
    AgentChatResponse,
    AgentContext,
    AgentResult,
    AgentSource,
    TraceSummary,
)
from agent_service.graph.blackboard import append_blackboard_entry, read_blackboard
from agent_service.graph.router import route_request
from agent_service.tools.registry import ToolRegistry


AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "property_search": PropertySearchAgent,
    "market_analysis": MarketAnalysisAgent,
    "legal_advisor": LegalAdvisorAgent,
    "investment_advisor": InvestmentAdvisorAgent,
    "project_agent": ProjectAgent,
    "news_agent": NewsAgent,
}


class OrchestratorAgent:
    """Orchestrator that replaces the static LangGraph workflow.

    Responsibilities:
      1. Route: Classify intent, select agents
      2. Dispatch: Run agents in parallel (each with own ReAct loop)
      3. Blackboard: Agents read/write shared state
      4. Synthesize: Combine results into final response
      5. Safety: Validate grounding and disclaimers
    """

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
        max_agent_iterations: int = 3,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_agent_iterations = max_agent_iterations
        self.settings = get_agent_settings()

    async def run(self, request: AgentChatRequest) -> AgentChatResponse:
        started = time.perf_counter()
        state: dict[str, Any] = {
            "request": request,
            "agent_blackboard": {"entries": []},
            "warnings": [],
        }

        # ── 1. Route ────────────────────────────────────────────
        if not request.message.strip():
            return AgentChatResponse(
                request_id=request.request_id,
                final_response=(
                    "Xin chào! Tôi có thể giúp bạn tìm kiếm bất động sản, "
                    "phân tích thị trường, hoặc tư vấn pháp lý. "
                    "Bạn muốn tìm hiểu về vấn đề gì?"
                ),
                agents_used=[],
                sources=[],
                suggested_actions=[
                    "Tìm bất động sản",
                    "Phân tích thị trường",
                    "Tư vấn pháp lý",
                ],
                trace_summary=TraceSummary(
                    intent="general",
                    agents=[],
                    source_count=0,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                ),
            )

        decision = await route_request(state)
        agents_to_run = decision.agents

        if decision.needs_clarification:
            return AgentChatResponse(
                request_id=request.request_id,
                final_response=decision.clarifying_question
                or "Bạn có thể bổ sung thêm tiêu chí được không?",
                agents_used=[],
                sources=[],
                suggested_actions=["Bổ sung ngân sách", "Bổ sung khu vực"],
                trace_summary=TraceSummary(
                    intent=decision.intent,
                    agents=agents_to_run,
                    source_count=0,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                ),
            )

        # ── 2. Dispatch agents in parallel ──────────────────────
        agent_results: dict[str, AgentResult] = {}
        agent_tasks = []

        for agent_name in agents_to_run:
            agent_cls = AGENT_CLASSES.get(agent_name)
            if agent_cls is None:
                continue

            agent = agent_cls(max_iterations=self.max_agent_iterations)
            context = AgentContext(
                agent_name=agent_name,
                query=request.message,
                normalized_query=request.message.lower(),
                routing_filters=decision.filters,
                user_preferences=request.user_preferences,
                locale=request.locale,
            )
            agent_tasks.append(
                agent.run(
                    context,
                    state,
                    tool_registry=self.tool_registry,
                    timeout_seconds=self.settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
                )
            )

        if agent_tasks:
            results_list = await asyncio.gather(*agent_tasks, return_exceptions=True)
            for i, result in enumerate(results_list):
                agent_name = agents_to_run[i] if i < len(agents_to_run) else f"agent_{i}"
                if isinstance(result, BaseException):
                    agent_results[agent_name] = AgentResult(
                        agent_name=agent_name,
                        status="failed",
                        content=f"Agent error: {result}",
                    )
                elif isinstance(result, AgentResult):
                    agent_results[agent_name] = result
                    if result.content:
                        state.update(
                            append_blackboard_entry(
                                state,
                                author=agent_name,
                                entry_type=f"{agent_name}_analysis",
                                content=result.content[:1000],
                                evidence_ids=result.evidence_ids_used,
                                confidence=(
                                    "high"
                                    if result.confidence == "high"
                                    else "medium"
                                ),
                                step_name="orchestrator_dispatch",
                            )
                        )

        # ── 3. Synthesize ───────────────────────────────────────
        parts: list[str] = []
        all_sources: list[AgentSource] = []
        all_warnings: list[str] = []

        for agent_name in agents_to_run:
            result = agent_results.get(agent_name)
            if result and result.content:
                parts.append(result.content)
                all_sources.extend(result.sources)
                all_warnings.extend(
                    w if isinstance(w, str) else w.code
                    for w in result.warnings
                )

        if not parts:
            final_response = (
                "Xin lỗi, tôi chưa thể xử lý yêu cầu này. "
                "Vui lòng thử lại với tiêu chí khác."
            )
        else:
            final_response = "\n\n".join(parts)

        # ── 4. Safety checks ────────────────────────────────────
        suggested_actions = self._suggest_actions(agents_to_run)
        if "legal_advisor" in agents_to_run and "khong thay the tu van luat su" not in final_response.lower():
            final_response += (
                "\n\n> ⚠️ Thông tin pháp lý chỉ mang tính tham khảo, "
                "không thay thế tư vấn luật sư chuyên nghiệp."
            )

        return AgentChatResponse(
            request_id=request.request_id,
            final_response=final_response,
            agents_used=agents_to_run,
            sources=list({s.id: s for s in all_sources if s.id}.values()),
            suggested_actions=suggested_actions,
            trace_summary=TraceSummary(
                intent=decision.intent,
                agents=agents_to_run,
                source_count=len(all_sources),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
            warnings=all_warnings,
        )

    def _suggest_actions(self, agents_used: list[str]) -> list[str]:
        suggestions = []
        if "property_search" in agents_used:
            suggestions.append("So sánh các lựa chọn")
            suggestions.append("Hỏi thêm về pháp lý")
        if "market_analysis" in agents_used:
            suggestions.append("Xem xu hướng khu vực khác")
        if "investment_advisor" in agents_used:
            suggestions.append("Xác nhận ngân sách đầu tư")
            suggestions.append("Kiểm tra pháp lý")
        if not suggestions:
            suggestions = ["Tìm bất động sản", "Phân tích thị trường", "Tư vấn pháp lý"]
        return suggestions[:5]
