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


class NewsAgent(BaseAgent):
    """Autonomous news analysis agent.

    Searches for real estate news articles and analyzes
    their impact on the market.

    Flow:
      1. think: Need news → call search_articles (non-legal)
      2. final_answer: Summarize news with impact analysis
    """

    def __init__(self, max_iterations: int = 2, use_llm: bool = False):
        super().__init__(agent_name="news_agent", max_iterations=max_iterations, use_llm=use_llm)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        has_news = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_news:
            return AgentThought(
                iteration=iteration,
                reasoning="Need to search for relevant news articles.",
                action="call_tool",
                tool_name="search_articles",
                tool_params={
                    "query": context.normalized_query,
                    "filters": {"exclude_category": "legal"},
                    "top_k": 15,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="News articles gathered. Ready to summarize.",
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
        all_articles: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                all_articles.extend(
                    item for item in results if isinstance(item, dict) and item.get("title")
                )
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_articles:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content="Chưa có tin tức mới về chủ đề này.",
                iterations=len(thoughts),
            )

        lines = ["📰 **Tin tức bất động sản:**\n"]
        for i, article in enumerate(all_articles[:5], 1):
            title = article.get("title", "Bài viết")
            snippet = article.get("snippet", article.get("text", ""))[:200]
            url = article.get("url", "")
            lines.append(f"**{i}. {title}**")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   🔗 {url}")
            lines.append("")

        sources = [
            AgentSource(
                type="article",
                id=article.get("id"),
                title=article.get("title"),
                url=article.get("url"),
                snippet=article.get("snippet", ""),
            )
            for article in all_articles[:5]
        ]

        return AgentResult(
            agent_name=self.agent_name,
            status="completed",
            content="\n".join(lines),
            evidence_ids_used=all_evidence_ids,
            sources=sources,
            confidence="medium",
            iterations=len(thoughts),
        )
