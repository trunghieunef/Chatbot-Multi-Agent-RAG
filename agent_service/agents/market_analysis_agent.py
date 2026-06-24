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
from agent_service.graph.charts import (
    build_district_comparison_chart,
    build_price_trend_chart,
)


class MarketAnalysisAgent(BaseAgent):
    """Autonomous market analysis agent.

    Flow:
      1. think: Need market data → call lookup_market_metrics
      2. think: Need timeseries for trend → call lookup_market_timeseries
      3. final_answer: Interpret trends, compare areas, provide context
    """

    def __init__(self, max_iterations: int = 3, use_llm: bool = False):
        super().__init__(agent_name="market_analysis", max_iterations=max_iterations, use_llm=use_llm)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_metrics = any(
            action.tool_result.get("metric") == "avg_price_per_m2"
            for action in previous_actions
            if action.action_type == "call_tool"
        )
        has_timeseries = any(
            "timeseries" in str(action.tool_result.get("results", ""))
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_metrics:
            return AgentThought(
                iteration=iteration,
                reasoning="Need current market snapshot for area comparison.",
                action="call_tool",
                tool_name="lookup_market_metrics",
                tool_params={"filters": context.routing_filters},
                confidence=0.9,
            )

        if not has_timeseries:
            return AgentThought(
                iteration=iteration,
                reasoning="Need historical timeseries to analyze price trends.",
                action="call_tool",
                tool_name="lookup_market_timeseries",
                tool_params={"filters": context.routing_filters},
                confidence=0.85,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient market data gathered.",
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
        metrics = []
        timeseries = []
        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        if item.get("metric"):
                            metrics.append(item)
                        elif item.get("snapshot_month"):
                            timeseries.append(item)

        if not metrics and not timeseries:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content=(
                    "Chưa có dữ liệu thị trường cho khu vực này. "
                    "Vui lòng thử khu vực khác hoặc quay lại sau."
                ),
                iterations=len(thoughts),
            )

        lines = ["📊 **Phân tích thị trường bất động sản:**\n"]
        if metrics:
            lines.append("**Giá trung bình hiện tại:**")
            for m in metrics[:5]:
                location = m.get("location", {})
                district = location.get("district", "") if isinstance(location, dict) else ""
                lines.append(
                    f"- {district or 'Khu vực'}: {m.get('value', 'N/A')} {m.get('unit', 'tr/m²')}"
                )

        if timeseries:
            lines.append("\n**Xu hướng giá:**")
            for ts in timeseries[:6]:
                month = ts.get("snapshot_month", "")
                avg = ts.get("avg_price_per_m2", "N/A")
                lines.append(f"- {month}: {avg} tr/m²")

        lines.append(
            "\n> ℹ️ Dữ liệu chỉ mang tính tham khảo, giá thực tế có thể khác tùy vị trí cụ thể."
        )

        filters = context.routing_filters or {}
        area = filters.get("district") or filters.get("city") or "khu vực"
        ptype = filters.get("property_type")
        trend_title = f"Biến động giá — {area}" + (f" ({ptype})" if ptype else "")
        comparison_title = f"So sánh giá theo quận — {filters.get('city') or 'khu vực'}"
        charts = [
            chart
            for chart in (
                build_price_trend_chart(timeseries, title=trend_title),
                build_district_comparison_chart(metrics, title=comparison_title),
            )
            if chart is not None
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=[],
            sources=[],
            confidence="medium",
            iterations=len(thoughts),
            charts=charts,
        )
