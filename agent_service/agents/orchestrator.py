from __future__ import annotations

from agent_service.agents.base import BaseAgent
from agent_service.agents.investment_advisor_agent import InvestmentAdvisorAgent
from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent
from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.agents.news_agent import NewsAgent
from agent_service.agents.project_agent import ProjectAgent
from agent_service.agents.property_search_agent import PropertySearchAgent

# Registry of specialist agent classes, keyed by the names the supervisor/router
# emit. The active graph (graph/agentic_workflow.py) dispatches specialists via
# this mapping; the former pure-Python OrchestratorAgent was removed when the
# LangGraph supervisor + specialist graph superseded it.
AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "property_search": PropertySearchAgent,
    "market_analysis": MarketAnalysisAgent,
    "legal_advisor": LegalAdvisorAgent,
    "investment_advisor": InvestmentAdvisorAgent,
    "project_agent": ProjectAgent,
    "news_agent": NewsAgent,
}
