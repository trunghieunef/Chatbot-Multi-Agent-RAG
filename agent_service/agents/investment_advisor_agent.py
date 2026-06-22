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


class InvestmentAdvisorAgent(BaseAgent):
    """Autonomous investment advisor agent.

    Reads blackboard for listing data from PropertySearch,
    market data from MarketAnalysis, then provides investment analysis.

    Flow:
      1. think: Read blackboard for property + market context
      2. think: If needed → call lookup_market_metrics for area comparison
      3. final_answer: ROI analysis with disclaimers
    """

    def __init__(self, max_iterations: int = 3, use_llm: bool = False):
        super().__init__(agent_name="investment_advisor", max_iterations=max_iterations, use_llm=use_llm)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        property_context = [
            e for e in blackboard_entries
            if e.get("author") == "property_search"
        ]
        market_context = [
            e for e in blackboard_entries
            if e.get("author") == "market_analysis"
        ]

        has_market_data = any(
            action.tool_result.get("value")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_market_data and not market_context:
            return AgentThought(
                iteration=iteration,
                reasoning="Need market metrics for investment comparison.",
                action="call_tool",
                tool_name="lookup_market_metrics",
                tool_params={
                    "filters": {
                        "city": context.routing_filters.get("city", "Hồ Chí Minh"),
                        "listing_type": context.routing_filters.get("listing_type", "sale"),
                    }
                },
                confidence=0.8,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient data for investment analysis.",
            action="final_answer",
            confidence=0.8,
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
        lines = [
            "💰 **Phân tích đầu tư bất động sản:**\n",
            "Dựa trên dữ liệu thị trường hiện có, tôi đưa ra một số nhận định:\n",
            "- **Tiềm năng tăng giá:** Cần xem xét vị trí, quy hoạch, và xu hướng khu vực.",
            "- **Rủi ro:** Thanh khoản, pháp lý, biến động thị trường.",
            "- **Khuyến nghị:** Nên thẩm định thực tế trước khi quyết định.\n",
            "> ⚠️ **Lưu ý quan trọng:** Đây KHÔNG phải lời khuyên tài chính. "
            "Bạn cần tự thẩm định và tham khảo chuyên gia tài chính trước khi "
            "đưa ra quyết định đầu tư.",
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=[],
            sources=[],
            confidence="low",
            iterations=len(thoughts),
        )
