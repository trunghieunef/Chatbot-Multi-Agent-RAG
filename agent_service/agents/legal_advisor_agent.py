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


class LegalAdvisorAgent(BaseAgent):
    """Autonomous legal advisor agent with domain guardrails.

    Only responds to real-estate legal questions. Uses
    search_articles for legal knowledge base retrieval.

    Flow:
      1. think: Check if query is in-domain → call search_articles
      2. act:   Execute search_articles via ToolRegistry
      3. observe: Has legal evidence? → final_answer
      4. final_answer: Present legal info with citations and disclaimer
    """

    LEGAL_DOMAIN_KEYWORDS = [
        "phap ly", "luat", "thu tuc", "cong chung", "so do", "so hong",
        "sang ten", "thue", "phi truoc ba", "chuyen nhuong", "thua ke",
        "the chap", "quy hoach", "xay dung", "dat dai", "nha o",
        "chung cu", "du an", "den bu", "giai toa", "hop dong",
        "giay chung nhan", "muaban", "chothue",
    ]

    def __init__(self, max_iterations: int = 3):
        super().__init__(agent_name="legal_advisor", max_iterations=max_iterations)

    def _is_in_domain(self, query: str) -> bool:
        query_lower = query.lower()
        return any(kw in query_lower for kw in self.LEGAL_DOMAIN_KEYWORDS)

    async def think(
        self,
        context: AgentContext,
        iteration: int,
        previous_actions: list[AgentAction],
        blackboard_entries: list[dict[str, Any]],
    ) -> AgentThought:
        if iteration == 0 and not self._is_in_domain(context.normalized_query):
            return AgentThought(
                iteration=iteration,
                reasoning="Query is not a legal question about real estate.",
                action="final_answer",
                confidence=0.95,
            )

        has_legal_evidence = any(
            action.tool_result.get("results")
            for action in previous_actions
            if action.action_type == "call_tool"
        )

        if not has_legal_evidence:
            return AgentThought(
                iteration=iteration,
                reasoning="Need to search legal knowledge base for relevant articles and regulations.",
                action="call_tool",
                tool_name="search_articles",
                tool_params={
                    "query": context.normalized_query,
                    "filters": {"category": "legal"},
                    "top_k": 15,
                    "rerank_to": 5,
                },
                confidence=0.9,
            )

        listing_context = ""
        for entry in blackboard_entries:
            if entry.get("author") == "property_search" and entry.get("type") == "listing_analysis":
                content = entry.get("content", "")
                if isinstance(content, str):
                    listing_context = content[:500]

        if listing_context and iteration < self.max_iterations - 1:
            return AgentThought(
                iteration=iteration,
                reasoning="Found property context from PropertySearch. Cross-referencing legal requirements.",
                action="call_tool",
                tool_name="search_articles",
                tool_params={
                    "query": f"{context.normalized_query} {listing_context}",
                    "filters": {"category": "legal"},
                    "top_k": 10,
                    "rerank_to": 3,
                },
                confidence=0.75,
            )

        return AgentThought(
            iteration=iteration,
            reasoning="Sufficient legal evidence gathered. Ready to provide legal advice.",
            action="final_answer",
            confidence=0.85,
        )

    async def act(
        self, thought: AgentThought, context: AgentContext
    ) -> AgentAction:
        import time
        started = time.perf_counter()

        if thought.action == "final_answer":
            if not self._is_in_domain(context.normalized_query):
                return AgentAction(
                    iteration=thought.iteration,
                    action_type="final_answer",
                    status="success",
                    tool_result={"out_of_domain": True},
                )
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
        if actions and actions[0].tool_result.get("out_of_domain"):
            return AgentResult(
                agent_name=self.agent_name,
                status="completed",
                content=(
                    "Tôi chỉ hỗ trợ các vấn đề pháp lý về bất động sản. "
                    "Vui lòng hỏi về mua bán, giấy tờ, thuế phí, hoặc các "
                    "vấn đề pháp lý liên quan đến nhà đất."
                ),
                iterations=len(thoughts),
            )

        all_articles: list[dict[str, Any]] = []
        all_evidence_ids: list[str] = []

        for action in actions:
            results = action.tool_result.get("results", [])
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict) and item.get("title"):
                        all_articles.append(item)
            for eid in action.evidence_ids:
                if eid not in all_evidence_ids:
                    all_evidence_ids.append(eid)

        if not all_articles:
            return AgentResult(
                agent_name=self.agent_name,
                status="no_evidence",
                content=(
                    "Chưa tìm thấy văn bản pháp lý liên quan đến câu hỏi của bạn. "
                    "Tôi khuyên bạn nên tham khảo ý kiến luật sư chuyên nghiệp."
                ),
                warnings=[],
                iterations=len(thoughts),
            )

        lines = ["⚖️ **Tư vấn pháp lý bất động sản:**\n"]
        for i, article in enumerate(all_articles[:5], 1):
            title = article.get("title", "Văn bản pháp luật")
            citation = article.get("citation", "")
            snippet = article.get("snippet", article.get("text", ""))[:300]
            lines.append(f"**{i}. {title}**")
            if citation:
                lines.append(f"   📜 Trích dẫn: {citation}")
            if snippet:
                lines.append(f"   {snippet}")
            lines.append("")

        lines.append(
            "> ⚠️ **Lưu ý:** Thông tin trên chỉ mang tính tham khảo, "
            "không thay thế tư vấn luật sư chuyên nghiệp. "
            "Vui lòng kiểm tra văn bản pháp luật mới nhất."
        )

        sources = [
            AgentSource(
                type="article",
                id=article.get("id"),
                title=article.get("title"),
                citation=article.get("citation"),
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
