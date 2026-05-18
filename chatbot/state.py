"""
Shared state schema for the LangGraph multi-agent workflow.

This state is passed between all agents and accumulates
information as the query is processed.
"""

from typing import Annotated, TypedDict
from langgraph.graph import MessagesState


class AgentResult(TypedDict, total=False):
    """Result from a single agent."""
    agent_name: str
    content: str
    sources: list[dict]
    confidence: float


class ChatState(MessagesState):
    """
    Shared state across all agents in the multi-agent RAG pipeline.

    Inherits MessagesState which provides `messages: list[BaseMessage]`.
    """

    # ─── Routing ───────────────────────────────────────────────
    user_query: str                          # Original user query
    intent: str                              # Classified intent
    target_agents: list[str]                 # Which agents should handle this

    # ─── Search Context ────────────────────────────────────────
    search_filters: dict                     # Extracted filters (price, area, location)
    retrieved_listings: list[dict]           # Listings found by Property Search
    retrieved_docs: list[dict]               # Knowledge docs retrieved

    # ─── Agent Results ─────────────────────────────────────────
    agent_results: dict[str, AgentResult]    # agent_name -> result

    # ─── Final Output ──────────────────────────────────────────
    final_response: str                      # Synthesized final answer
    sources: list[dict]                      # Citation sources
    suggested_actions: list[str]             # Follow-up suggestions for user
    agent_used: str                          # Summary of agents that contributed
