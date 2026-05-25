"""
Legal Advisor Agent — Real estate legal consultation.

Calls hybrid search restricted to legal articles, then synthesizes a cited
answer via the legal_synthesis tool.
"""

from chatbot.state import ChatState
from chatbot.tools.hybrid_search import hybrid_search
from chatbot.tools.legal_synthesis import synthesize_legal_answer


async def legal_advisor_node(state: ChatState) -> dict:
    query = state.get("user_query", "")
    filters = dict(state.get("search_filters", {}))
    filters["category"] = "legal"

    chunks = await hybrid_search(query=query, filters=filters, parent_type="article")
    answer = await synthesize_legal_answer(query, chunks)

    sources: list[str] = []
    for chunk in chunks:
        citation = chunk.get("citation") or {}
        if citation.get("doc_slug"):
            sources.append(f"{citation['doc_slug']} - Điều {citation.get('dieu_number')}")

    return {
        "agent_results": {
            **state.get("agent_results", {}),
            "legal_advisor": {
                "agent_name": "legal_advisor",
                "content": answer,
                "sources": sources,
                "confidence": 0.8 if chunks else 0.3,
            },
        },
    }
