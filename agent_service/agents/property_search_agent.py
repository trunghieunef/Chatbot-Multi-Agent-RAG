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
from agent_service.graph.charts import build_comparison_table


class PropertySearchAgent(BaseAgent):
    """Autonomous property search agent with its own ReAct loop.

    Flow:
      1. think: "Do I have listings? If not → call search_listings"
      2. act:   Execute search_listings via ToolRegistry
      3. observe: "Do I have ≥1 result? If yes → final_answer"
      4. (optional) think: "Need market comparison → call lookup_market_metrics"
      5. final_answer: Format listings with prices and area
    """

    def __init__(self, max_iterations: int = 3, use_llm: bool = False):
        super().__init__(agent_name="property_search", max_iterations=max_iterations, use_llm=use_llm)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_listings = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_listings:
            return AgentThought(
                iteration=iteration,
                reasoning="No listings yet. Need to search for properties matching the query.",
                action="call_tool",
                tool_name="search_listings",
                tool_params={
                    "query": context.normalized_query,
                    "filters": context.routing_filters,
                    "top_k": 20,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        # If we have listings but haven't compared to market, do that
        has_market_data = any(
            action.tool_result.get("metric") == "avg_price_per_m2"
            for action in previous_actions
            if action.action_type == "call_tool"
        )
        if not has_market_data and context.routing_filters:
            city = context.routing_filters.get("city")
            district = context.routing_filters.get("district")
            if city:
                return AgentThought(
                    iteration=iteration,
                    reasoning="Have listings, now compare with market average for context.",
                    action="call_tool",
                    tool_name="lookup_market_metrics",
                    tool_params={
                        "filters": {
                            "city": city,
                            "district": district,
                            "listing_type": context.routing_filters.get("listing_type", "sale"),
                        }
                    },
                    confidence=0.8,
                )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient data gathered. Ready to present listings.",
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
                duration_ms=0.0,
            )

        try:
            result = await self.call_tool(
                tool_name=thought.tool_name,
                tool_params=thought.tool_params or {},
                context=context,
            )
            evidence_ids = result.get("evidence_ids", [])
            return AgentAction(
                iteration=thought.iteration,
                action_type="call_tool",
                status="success",
                tool_result=result,
                evidence_ids=evidence_ids if isinstance(evidence_ids, list) else [],
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
        all_listings: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []
        market_data: list[dict[str, Any]] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict):
                        if item.get("metric"):
                            market_data.append(item)
                        elif item.get("title"):
                            all_listings.append(item)
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_listings:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content=(
                    "Chưa tìm thấy bất động sản nào phù hợp với tiêu chí của bạn. "
                    "Vui lòng thử mở rộng khu vực tìm kiếm hoặc điều chỉnh ngân sách."
                ),
                warnings=[],
                iterations=len(thoughts),
            )

        # ── Build listing cards ──────────────────────────────────
        lines = ["🏠 **Kết quả tìm kiếm bất động sản:**\n"]
        for i, listing in enumerate(all_listings[:10], 1):
            title = listing.get("title", "Không có tiêu đề")
            price = listing.get("price_text", "Liên hệ")
            area = listing.get("area_text", "N/A")
            district = listing.get("district", "")
            city = listing.get("city", "")
            location = f"{district}, {city}" if district else city
            ppm = listing.get("price_per_m2")
            ppm_str = f" - {ppm:.1f} tr/m²" if ppm else ""
            listing_id = listing.get("id", "")
            listing_url = listing.get("url", "")
            detail_link = listing_url or f"/nha-dat-ban/{listing_id}" if listing_id else ""

            lines.append(
                f"**{i}. {title}**\n"
                f"   💰 {price} | 📐 {area} | 📍 {location}{ppm_str}\n"
            )

            # Images
            images = listing.get("images", [])
            if images:
                for img_url in images[:2]:
                    lines.append(f"   ![Ảnh]({img_url})")
                lines.append("")

            # Link
            if detail_link:
                lines.append(f"   🔗 [Xem chi tiết]({detail_link})\n")

        # ── Market context (area average price/m²) ───────────────
        area_avg: float | None = None
        avg_prices = [
            float(m.get("value", 0))
            for m in (market_data or [])
            if m.get("metric") == "avg_price_per_m2" and m.get("value")
        ]
        if avg_prices:
            area_avg = sum(avg_prices) / len(avg_prices)
            lines.append(f"\n📊 **Giá trung bình khu vực:** {area_avg:.1f} tr/m²")
            lines.append(
                "> ℹ️ Giá/m² tính từ diện tích và giá listing. "
                "Giá thực tế có thể thay đổi khi thương lượng."
            )

        sources = [
            AgentSource(
                type="listing",
                id=listing.get("id"),
                title=listing.get("title"),
                url=listing.get("url") or f"/nha-dat-ban/{listing.get('id')}" if listing.get("id") else None,
                location={"district": listing.get("district"), "city": listing.get("city")},
                metadata={
                    "price_text": listing.get("price_text"),
                    "area_text": listing.get("area_text"),
                    "images": listing.get("images", []),
                    "price_per_m2": listing.get("price_per_m2"),
                },
            )
            for listing in all_listings[:10]
        ]

        query_text = f"{context.normalized_query or ''} {context.query or ''}".lower()
        wants_comparison = any(
            keyword in query_text
            for keyword in ("so sanh", "so sánh", "compare", "doi chieu", "đối chiếu")
        )
        comparison = build_comparison_table(
            all_listings, area_avg_price_per_m2=area_avg, auto_open=wants_comparison
        )

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=sources,
            confidence="high" if all_listings else "low",
            iterations=len(thoughts),
            charts=[comparison] if comparison else [],
        )
