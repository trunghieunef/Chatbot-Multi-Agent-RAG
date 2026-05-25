"""
LangGraph multi-agent workflow for real estate chatbot.

Defines the graph: Router → [Agents] → Synthesizer → Response

Graph flow:
    1. Router Agent analyzes the query and decides which agent(s) to invoke
    2. Selected agent(s) run in parallel (if multiple)
    3. Response Synthesizer combines agent results into a final answer
"""

from langgraph.graph import StateGraph, END

from chatbot.state import ChatState
from chatbot.agents.router import router_node
from chatbot.agents.property_search import property_search_node
from chatbot.agents.market_analysis import market_analysis_node
from chatbot.agents.legal_advisor import legal_advisor_node
from chatbot.agents.investment_advisor import investment_advisor_node


def synthesizer_node(state: ChatState) -> dict:
    """
    Combine results from all agents into a final response.
    """
    agent_results = state.get("agent_results", {})

    if not agent_results:
        return {
            "final_response": "Xin lỗi, tôi không thể xử lý câu hỏi này. Vui lòng thử lại.",
            "agent_used": "none",
        }

    # Combine all agent responses
    parts = []
    all_sources = []
    agents_used = []

    for agent_name, result in agent_results.items():
        if result.get("content"):
            parts.append(result["content"])
            agents_used.append(agent_name)
            if result.get("sources"):
                all_sources.extend(result["sources"])

    final = "\n\n".join(parts) if parts else "Không có kết quả phù hợp."

    return {
        "final_response": final,
        "sources": all_sources,
        "agent_used": ", ".join(agents_used),
        "suggested_actions": _generate_suggestions(state),
    }


def _generate_suggestions(state: ChatState) -> list[str]:
    """Generate follow-up suggestions based on the query context."""
    intent = state.get("intent", "")
    suggestions = []

    if "property" in intent:
        suggestions.extend([
            "Xem thêm bất động sản tương tự",
            "So sánh giá khu vực lân cận",
            "Tư vấn pháp lý mua nhà",
        ])
    elif "market" in intent:
        suggestions.extend([
            "Xem chi tiết khu vực cụ thể",
            "So sánh với quý trước",
            "Gợi ý đầu tư",
        ])
    elif "legal" in intent:
        suggestions.extend([
            "Thủ tục công chứng",
            "Tính thuế chuyển nhượng",
            "Kiểm tra pháp lý dự án",
        ])
    elif "investment" in intent:
        suggestions.extend([
            "Phân tích ROI cụ thể",
            "So sánh kênh đầu tư",
            "Xu hướng thị trường",
        ])
    else:
        suggestions.extend([
            "Tìm nhà theo nhu cầu",
            "Phân tích thị trường",
            "Tư vấn pháp lý",
        ])

    return suggestions[:3]


def route_to_agents(state: ChatState) -> list[str]:
    """
    Conditional edge: route to the appropriate agent(s) based on Router output.
    """
    target_agents = state.get("target_agents", ["property_search"])

    # Map agent names to node names
    agent_map = {
        "property_search": "property_search",
        "market_analysis": "market_analysis",
        "legal_advisor": "legal_advisor",
        "investment_advisor": "investment_advisor",
    }

    routes = []
    for agent in target_agents:
        if agent in agent_map:
            routes.append(agent_map[agent])

    return routes if routes else ["property_search"]


def build_graph() -> StateGraph:
    """
    Build the LangGraph workflow.

    Graph structure:
        START → router → [property_search, market_analysis, legal_advisor, investment_advisor] → synthesizer → END
    """
    graph = StateGraph(ChatState)

    # Add nodes
    graph.add_node("router", router_node)
    graph.add_node("property_search", property_search_node)
    graph.add_node("market_analysis", market_analysis_node)
    graph.add_node("legal_advisor", legal_advisor_node)
    graph.add_node("investment_advisor", investment_advisor_node)
    graph.add_node("synthesizer", synthesizer_node)

    # Entry point
    graph.set_entry_point("router")

    # Conditional routing from router to agents
    graph.add_conditional_edges(
        "router",
        route_to_agents,
        {
            "property_search": "property_search",
            "market_analysis": "market_analysis",
            "legal_advisor": "legal_advisor",
            "investment_advisor": "investment_advisor",
        },
    )

    # All agents feed into synthesizer
    graph.add_edge("property_search", "synthesizer")
    graph.add_edge("market_analysis", "synthesizer")
    graph.add_edge("legal_advisor", "synthesizer")
    graph.add_edge("investment_advisor", "synthesizer")

    # Synthesizer → END
    graph.add_edge("synthesizer", END)

    return graph


# Compiled graph (singleton)
chat_graph = build_graph().compile()


async def run_chat_pipeline(query: str, session_id: str = None) -> dict:
    """
    Run the multi-agent RAG pipeline for a user query.

    Returns:
        dict with keys: final_response, sources, agent_used, suggested_actions
    """
    initial_state = {
        "messages": [],
        "user_query": query,
        "intent": "",
        "target_agents": [],
        "search_filters": {},
        "retrieved_listings": [],
        "retrieved_docs": [],
        "agent_results": {},
        "final_response": "",
        "sources": [],
        "suggested_actions": [],
        "agent_used": "",
    }

    result = await chat_graph.ainvoke(initial_state)

    return {
        "final_response": result.get("final_response", ""),
        "sources": result.get("sources", []),
        "agent_used": result.get("agent_used", ""),
        "suggested_actions": result.get("suggested_actions", []),
    }
