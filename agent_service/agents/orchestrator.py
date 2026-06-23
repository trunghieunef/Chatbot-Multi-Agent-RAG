from __future__ import annotations

import json
import time
from typing import Any

from agent_service.agents.base import BaseAgent
from agent_service.agents.investment_advisor_agent import InvestmentAdvisorAgent
from agent_service.agents.legal_advisor_agent import LegalAdvisorAgent
from agent_service.agents.market_analysis_agent import MarketAnalysisAgent
from agent_service.agents.news_agent import NewsAgent
from agent_service.agents.project_agent import ProjectAgent
from agent_service.agents.property_search_agent import PropertySearchAgent
from agent_service.config import get_agent_settings
from agent_service.contracts import (
    AgentAction,
    AgentChatRequest,
    AgentChatResponse,
    AgentContext,
    AgentResult,
    AgentSource,
    AgentThought,
    TraceSummary,
)
from agent_service.graph.blackboard import append_blackboard_entry, read_blackboard
from agent_service.graph.router import route_request
from agent_service.llm.gemini import GeminiClient
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
    """Router, round-based agent coordinator, blackboard owner, synthesizer."""

    def __init__(
        self,
        *,
        tool_registry: ToolRegistry | None = None,
        max_agent_iterations: int = 3,
        use_llm: bool = False,
    ):
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_agent_iterations = max_agent_iterations
        self.settings = get_agent_settings()
        self.use_llm = use_llm and bool(self.settings.GEMINI_API_KEY)
        self._llm_client: GeminiClient | None = (
            GeminiClient() if self.use_llm else None
        )

    async def run(self, request: AgentChatRequest) -> AgentChatResponse:
        started = time.perf_counter()
        state: dict[str, Any] = {
            "request": request,
            "agent_blackboard": {"entries": []},
            "evidence_by_id": {},
            "warnings": [],
        }

        if not request.message.strip():
            return AgentChatResponse(
                request_id=request.request_id,
                final_response=(
                    "Xin chao! Toi co the giup ban tim kiem bat dong san, "
                    "phan tich thi truong, hoac tu van phap ly. "
                    "Ban muon tim hieu ve van de gi?"
                ),
                agents_used=[],
                sources=[],
                suggested_actions=[
                    "Tim bat dong san",
                    "Phan tich thi truong",
                    "Tu van phap ly",
                ],
                trace_summary=TraceSummary(
                    intent="general",
                    agents=[],
                    source_count=0,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                ),
                full_trace={
                    "orchestration_mode": "round_based",
                    "router_decision": {},
                    "round_count": 0,
                    "rounds": [],
                    "blackboard": state["agent_blackboard"],
                    "synthesizer_mode": "empty_query",
                },
            )

        decision = await route_request(state)
        agents_to_run = decision.agents
        state["router_decision"] = decision.model_dump(mode="python")
        state["normalized_query"] = request.message.lower()
        state["routing_filters"] = decision.filters

        if decision.needs_clarification:
            return AgentChatResponse(
                request_id=request.request_id,
                final_response=decision.clarifying_question
                or "Ban co the bo sung them tieu chi duoc khong?",
                agents_used=[],
                sources=[],
                suggested_actions=["Bo sung ngan sach", "Bo sung khu vuc"],
                trace_summary=TraceSummary(
                    intent=decision.intent,
                    agents=agents_to_run,
                    source_count=0,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                ),
                full_trace={
                    "orchestration_mode": "round_based",
                    "router_decision": decision.model_dump(mode="json"),
                    "round_count": 0,
                    "rounds": [],
                    "blackboard": state["agent_blackboard"],
                    "synthesizer_mode": "clarification",
                },
            )

        agent_results, rounds_trace = await self._run_agent_rounds(
            request=request,
            agents_to_run=agents_to_run,
            filters=decision.filters,
            state=state,
        )
        all_sources = self._collect_sources(agents_to_run, agent_results)
        all_warnings = self._collect_warnings(agents_to_run, agent_results, state)
        final_response, synthesizer_mode = await self._synthesize_response(
            request=request,
            decision=decision,
            agents_to_run=agents_to_run,
            agent_results=agent_results,
            sources=all_sources,
            warnings=all_warnings,
            state=state,
        )

        suggested_actions = self._suggest_actions(agents_to_run)
        if (
            "legal_advisor" in agents_to_run
            and "khong thay the tu van luat su" not in final_response.lower()
        ):
            final_response += (
                "\n\n> Thong tin phap ly chi mang tinh tham khao, "
                "khong thay the tu van luat su chuyen nghiep."
            )

        return AgentChatResponse(
            request_id=request.request_id,
            final_response=final_response,
            agents_used=agents_to_run,
            sources=all_sources,
            suggested_actions=suggested_actions,
            trace_summary=TraceSummary(
                intent=decision.intent,
                agents=agents_to_run,
                source_count=len(all_sources),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                warnings=all_warnings,
            ),
            full_trace={
                "orchestration_mode": "round_based",
                "router_decision": decision.model_dump(mode="json"),
                "round_count": len(rounds_trace),
                "rounds": rounds_trace,
                "blackboard": state.get("agent_blackboard", {"entries": []}),
                "synthesizer_mode": synthesizer_mode,
            },
        )

    async def _run_agent_rounds(
        self,
        *,
        request: AgentChatRequest,
        agents_to_run: list[str],
        filters: dict[str, Any],
        state: dict[str, Any],
    ) -> tuple[dict[str, AgentResult], list[dict[str, Any]]]:
        agent_results: dict[str, AgentResult] = {}
        agent_instances: dict[str, BaseAgent] = {}
        contexts: dict[str, AgentContext] = {}
        thoughts_by_agent: dict[str, list[AgentThought]] = {}
        actions_by_agent: dict[str, list[AgentAction]] = {}
        active_agents: list[str] = []
        rounds_trace: list[dict[str, Any]] = []

        for agent_name in agents_to_run:
            agent_cls = AGENT_CLASSES.get(agent_name)
            if agent_cls is None:
                continue
            agent_instances[agent_name] = agent_cls(
                max_iterations=self.max_agent_iterations,
                use_llm=self.use_llm,
            )
            contexts[agent_name] = AgentContext(
                agent_name=agent_name,
                query=request.message,
                normalized_query=request.message.lower(),
                routing_filters=filters,
                user_preferences=request.user_preferences,
                locale=request.locale,
            )
            thoughts_by_agent[agent_name] = []
            actions_by_agent[agent_name] = []
            active_agents.append(agent_name)

        for round_index in range(self.max_agent_iterations):
            if not active_agents:
                break

            snapshot_state = {
                "agent_blackboard": {
                    "entries": [
                        dict(entry)
                        for entry in (
                            state.get("agent_blackboard", {}).get("entries", [])
                        )
                    ]
                },
                "evidence_by_id": dict(state.get("evidence_by_id") or {}),
            }
            events: list[dict[str, Any]] = []

            for agent_name in list(active_agents):
                agent = agent_instances[agent_name]
                iteration = len(thoughts_by_agent[agent_name])
                thought, action, result = await agent.run_one_iteration(
                    contexts[agent_name],
                    snapshot_state,
                    thoughts=thoughts_by_agent[agent_name],
                    actions=actions_by_agent[agent_name],
                    iteration=iteration,
                    tool_registry=self.tool_registry,
                    llm_client=self._llm_client,
                )
                events.append(
                    self._trace_agent_step(
                        round_index=round_index,
                        agent_name=agent_name,
                        thought=thought,
                        action=action,
                        result=result,
                    )
                )

                if action is not None and action.action_type == "call_tool":
                    self._append_tool_observation(
                        state=state,
                        agent_name=agent_name,
                        thought=thought,
                        action=action,
                        round_index=round_index,
                    )

                if result is not None:
                    agent_results[agent_name] = result
                    active_agents.remove(agent_name)
                    self._append_agent_result(
                        state=state,
                        agent_name=agent_name,
                        result=result,
                        round_index=round_index,
                    )

            rounds_trace.append({"round": round_index, "events": events})

        for agent_name in list(active_agents):
            result = agent_instances[agent_name].build_result(
                contexts[agent_name],
                thoughts_by_agent[agent_name],
                actions_by_agent[agent_name],
            )
            agent_results[agent_name] = result
            state.setdefault("warnings", []).append(
                f"round_budget_exhausted:{agent_name}"
            )
            self._append_agent_result(
                state=state,
                agent_name=agent_name,
                result=result,
                round_index=self.max_agent_iterations,
            )

        return agent_results, rounds_trace

    def _trace_agent_step(
        self,
        *,
        round_index: int,
        agent_name: str,
        thought: AgentThought | None,
        action: AgentAction | None,
        result: AgentResult | None,
    ) -> dict[str, Any]:
        tool_result = action.tool_result if action is not None else {}
        results = tool_result.get("results") if isinstance(tool_result, dict) else None
        return {
            "round": round_index,
            "agent": agent_name,
            "thought_action": thought.action if thought is not None else None,
            "tool_name": thought.tool_name if thought is not None else None,
            "action_status": action.status if action is not None else None,
            "result_count": len(results) if isinstance(results, list) else 0,
            "final_status": result.status if result is not None else None,
        }

    def _append_tool_observation(
        self,
        *,
        state: dict[str, Any],
        agent_name: str,
        thought: AgentThought | None,
        action: AgentAction,
        round_index: int,
    ) -> None:
        tool_result = action.tool_result or {}
        results = tool_result.get("results")
        result_count = len(results) if isinstance(results, list) else 0
        state.update(
            append_blackboard_entry(
                state,
                author=agent_name,
                entry_type="tool_observation",
                content={
                    "tool_name": thought.tool_name if thought is not None else None,
                    "status": action.status,
                    "result_count": result_count,
                    "error_message": action.error_message,
                    "summary": str(tool_result)[:700],
                },
                evidence_ids=action.evidence_ids,
                confidence="medium" if action.status == "success" else "low",
                step_name=f"round_{round_index}_tool",
            )
        )

    def _append_agent_result(
        self,
        *,
        state: dict[str, Any],
        agent_name: str,
        result: AgentResult,
        round_index: int,
    ) -> None:
        if not result.content:
            return
        state.update(
            append_blackboard_entry(
                state,
                author=agent_name,
                entry_type=f"{agent_name}_final",
                content=result.content[:1000],
                evidence_ids=result.evidence_ids_used,
                confidence="high" if result.confidence == "high" else "medium",
                step_name=f"round_{round_index}_final",
            )
        )

    def _collect_sources(
        self,
        agents_to_run: list[str],
        agent_results: dict[str, AgentResult],
    ) -> list[AgentSource]:
        sources: list[AgentSource] = []
        for agent_name in agents_to_run:
            result = agent_results.get(agent_name)
            if result is not None:
                sources.extend(result.sources)

        deduped: dict[str, AgentSource] = {}
        for index, source in enumerate(sources):
            key = f"{source.type}:{source.id or source.url or source.title or index}"
            deduped[key] = source
        return list(deduped.values())

    def _collect_warnings(
        self,
        agents_to_run: list[str],
        agent_results: dict[str, AgentResult],
        state: dict[str, Any],
    ) -> list[str]:
        warnings = [str(warning) for warning in state.get("warnings", [])]
        for agent_name in agents_to_run:
            result = agent_results.get(agent_name)
            if result is None:
                continue
            warnings.extend(
                warning if isinstance(warning, str) else warning.code
                for warning in result.warnings
            )
        return list(dict.fromkeys(warnings))

    async def _synthesize_response(
        self,
        *,
        request: AgentChatRequest,
        decision,
        agents_to_run: list[str],
        agent_results: dict[str, AgentResult],
        sources: list[AgentSource],
        warnings: list[str],
        state: dict[str, Any],
    ) -> tuple[str, str]:
        fallback = self._fallback_synthesis(agents_to_run, agent_results)
        if self._llm_client is None or not fallback.strip():
            return fallback, "fallback"

        prompt = self._build_synthesizer_prompt(
            request=request,
            decision=decision,
            agent_results=agent_results,
            sources=sources,
            warnings=warnings,
            state=state,
        )
        try:
            result = await self._llm_client.generate_text_with_usage(
                prompt,
                timeout_seconds=self.settings.AGENT_LLM_TIMEOUT_SECONDS,
            )
            text = (getattr(result, "text", "") or "").strip()
            if text:
                return text, "llm"
        except Exception:
            return fallback, "fallback"
        return fallback, "fallback"

    def _fallback_synthesis(
        self,
        agents_to_run: list[str],
        agent_results: dict[str, AgentResult],
    ) -> str:
        parts = [
            result.content
            for agent_name in agents_to_run
            if (result := agent_results.get(agent_name)) and result.content
        ]
        if parts:
            return "\n\n".join(parts)
        return (
            "Xin loi, toi chua the xu ly yeu cau nay. "
            "Vui long thu lai voi tieu chi khac."
        )

    def _build_synthesizer_prompt(
        self,
        *,
        request: AgentChatRequest,
        decision,
        agent_results: dict[str, AgentResult],
        sources: list[AgentSource],
        warnings: list[str],
        state: dict[str, Any],
    ) -> str:
        result_payload = {
            name: result.model_dump(mode="json")
            for name, result in agent_results.items()
        }
        source_payload = [source.model_dump(mode="json") for source in sources]
        blackboard_entries = read_blackboard(state, max_entries=20)
        return "\n".join(
            [
                "Ban la synthesizer cho he thong Agentic RAG bat dong san.",
                "Tra loi bang tieng Viet, mach lac, dua tren evidence ben duoi.",
                "Khong duoc bia listing, bai viet, gia, hoac thong tin phap ly khong co trong evidence/sources.",
                "Neu evidence thieu, noi ro gioi han va goi y cach hoi tiep.",
                "",
                f"User query: {request.message}",
                f"Intent: {decision.intent}",
                f"Agents: {', '.join(decision.agents)}",
                f"Filters: {json.dumps(decision.filters, ensure_ascii=False)}",
                f"Warnings: {json.dumps(warnings, ensure_ascii=False)}",
                "",
                "Blackboard:",
                json.dumps(blackboard_entries, ensure_ascii=False, indent=2),
                "",
                "Agent results:",
                json.dumps(result_payload, ensure_ascii=False, indent=2),
                "",
                "Sources:",
                json.dumps(source_payload, ensure_ascii=False, indent=2),
            ]
        )

    def _suggest_actions(self, agents_used: list[str]) -> list[str]:
        suggestions = []
        if "property_search" in agents_used:
            suggestions.append("So sanh cac lua chon")
            suggestions.append("Hoi them ve phap ly")
        if "market_analysis" in agents_used:
            suggestions.append("Xem xu huong khu vuc khac")
        if "investment_advisor" in agents_used:
            suggestions.append("Xac nhan ngan sach dau tu")
            suggestions.append("Kiem tra phap ly")
        if not suggestions:
            suggestions = [
                "Tim bat dong san",
                "Phan tich thi truong",
                "Tu van phap ly",
            ]
        return suggestions[:5]
