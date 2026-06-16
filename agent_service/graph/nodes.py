from __future__ import annotations

import asyncio
import time
from typing import Any

from agent_service.agents.llm_specialists import run_llm_or_deterministic_specialist
from agent_service.agents.specialists import (
    run_investment_agent,
    run_legal_agent,
    run_market_agent,
    run_news_agent,
    run_project_agent,
    run_property_agent,
)
from agent_service.contracts import (
    AgentSource,
    Evidence,
    StructuredWarning,
)
from agent_service.config import get_agent_settings
from agent_service.graph.blackboard import append_blackboard_entry
from agent_service.graph.committee import build_committee_review
from agent_service.graph.investment_model import (
    build_investment_case,
    calculate_investment_metrics,
    resolve_investment_assumptions,
)
from agent_service.graph.memory_extraction import extract_memory_proposals
from agent_service.graph.memory_filters import derive_memory_filters
from agent_service.graph.retrieval_planner import (
    build_retrieval_plan,
    execute_retrieval_plan,
)
from agent_service.graph.query_understanding import build_query_understanding
from agent_service.graph.router import _strip_accents, route_request
from agent_service.graph.state import AgentGraphState
from agent_service.graph.synthesis import (
    format_investment_scorecard,
    synthesize_final_answer,
)
from agent_service.llm.gemini import GeminiClient
from agent_service.tools.readiness import build_readiness_snapshot


SOURCE_BACKED_AGENTS = {
    "legal_advisor",
    "news_agent",
    "project_agent",
    "property_search",
}

NO_SOURCE_WARNINGS = {
    "legal_kb_not_ready",
    "insufficient_legal_evidence",
    "listing_source_not_ready",
    "no_legal_evidence",
    "no_listing_evidence",
    "no_news_evidence",
    "no_project_evidence",
    "project_source_not_ready",
}


def _trace_step(name: str, started: float, output: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_name": name,
        "status": "success",
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "output": output,
    }


def _append_trace(
    state: AgentGraphState,
    step_name: str,
    start_time: float,
    output: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    trace_steps = list(state.get("trace_steps", []))
    trace_steps.append(_trace_step(step_name, start_time, output or {}))
    return trace_steps


def _warning_key(warning: Any) -> tuple[Any, ...]:
    if isinstance(warning, StructuredWarning):
        return (
            "structured",
            warning.code,
            warning.domain,
            warning.message,
            warning.retryable,
            repr(sorted(warning.details.items())),
        )
    if isinstance(warning, dict):
        return (
            "dict",
            warning.get("code"),
            warning.get("domain"),
            warning.get("message"),
            warning.get("retryable"),
            repr(sorted(warning.get("details", {}).items()))
            if isinstance(warning.get("details"), dict)
            else repr(warning.get("details")),
        )
    return ("string", str(warning))


def _warning_text(warning: Any) -> str:
    if isinstance(warning, StructuredWarning):
        return warning.code
    if isinstance(warning, dict):
        return str(warning.get("code") or warning.get("message") or warning)
    return str(warning)


def _dedupe_warnings(warnings: list[Any]) -> list[Any]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[Any] = []
    for warning in warnings:
        key = _warning_key(warning)
        if key in seen:
            continue
        seen.add(key)
        unique.append(warning)
    return unique


def _source_key(source: AgentSource) -> tuple[Any, ...]:
    return (
        source.type,
        source.id,
        source.product_id,
        source.url,
        source.title,
    )


def _dedupe_sources(sources: list[AgentSource]) -> list[AgentSource]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[AgentSource] = []
    for source in sources:
        key = _source_key(source)
        if key in seen:
            continue
        seen.add(key)
        unique.append(source)
    return unique


def _claim_requires_evidence(claim: Any) -> bool:
    if not isinstance(claim, dict):
        return True
    return claim.get("type") not in {"caveat", "disclaimer", "missing_evidence"}


def _claim_evidence_ids(claim: Any) -> set[str]:
    if not isinstance(claim, dict):
        return set()

    evidence_ids: set[str] = set()
    raw_ids = claim.get("evidence_ids", [])
    if isinstance(raw_ids, (list, tuple, set)):
        evidence_ids.update(str(value) for value in raw_ids if value is not None)
    elif raw_ids is not None:
        evidence_ids.add(str(raw_ids))

    raw_id = claim.get("evidence_id")
    if raw_id is not None:
        evidence_ids.add(str(raw_id))
    return evidence_ids


def _invalid_claim_ratio(claims: list[Any], valid_ids: set[str]) -> float:
    checked = [claim for claim in claims if _claim_requires_evidence(claim)]
    if not checked:
        return 0.0

    invalid = [
        claim
        for claim in checked
        if not (
            (claim_ids := _claim_evidence_ids(claim))
            and claim_ids.issubset(valid_ids)
        )
    ]
    return len(invalid) / len(checked)


def _valid_claim_evidence_ids(
    *,
    agent: str,
    evidence_by_id: dict[str, Evidence],
    evidence_for_agent: dict[str, list[str]],
) -> set[str]:
    return {
        evidence_id
        for evidence_id, evidence in evidence_by_id.items()
        if _is_evidence_assigned_to_agent(
            evidence_id=evidence_id,
            agent=agent,
            evidence=evidence,
            evidence_for_agent=evidence_for_agent,
        )
    }


def _fallback_content_for_agent(result: dict[str, Any]) -> str:
    fallback = result.get("fallback_content")
    if fallback:
        return str(fallback)
    return "Chua co du bang chung hop le de tra loi an toan."


def _response_with_grounding_fallbacks(
    *,
    agents_to_run: list[str],
    agent_results: dict[str, dict[str, Any]],
    fallback_agents: set[str],
    current_response: str,
) -> str:
    parts: list[str] = []
    for agent in agents_to_run:
        result = agent_results.get(agent) or {}
        if agent in fallback_agents:
            content = _fallback_content_for_agent(result)
        else:
            content = str(result.get("content") or "")
        if content:
            parts.append(content)
    return "\n\n".join(parts) if parts else current_response


def _warning(
    code: str,
    domain: str | None,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> StructuredWarning:
    return StructuredWarning(
        code=code,
        domain=domain,
        message=message,
        retryable=False,
        details=details or {},
    )


def _compact_conversation_context(request) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    for item in request.conversation_context[-6:]:
        content = (item.content or "").strip()
        if not content:
            continue
        compact.append({"role": item.role, "content": content[:500]})
    return compact

def context_builder(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    request = state["request"]
    normalized_query = _strip_accents(request.message)
    compact_context = _compact_conversation_context(request)
    return {
        "normalized_query": normalized_query,
        "compact_context": compact_context,
        "trace_steps": _append_trace(
            state,
            "context_builder",
            start_time,
            {
                "context_items": len(request.conversation_context),
                "compact_context_items": len(compact_context),
            },
        ),
    }

async def readiness_checker(state: AgentGraphState) -> AgentGraphState:
    started = time.perf_counter()
    readiness = await build_readiness_snapshot()
    steps = state.get("trace_steps", [])
    steps.append(_trace_step("readiness_checker", started, readiness))
    return {**state, "readiness": readiness, "trace_steps": steps}


async def router_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    decision = await route_request(state)
    return {
        "intent": decision.intent,
        "agents_to_run": decision.agents,
        "routing_filters": decision.filters,
        "warnings": [*state.get("warnings", []), *decision.warnings],
        "trace_steps": _append_trace(
            state,
            "router",
            start_time,
            decision.model_dump(mode="json"),
        ),
    }


async def query_understanding_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    settings = get_agent_settings()
    understanding = await build_query_understanding(state)
    memory_filters = None
    if settings.AGENT_MEMORY_FILTERS_ENABLED and not state.get("force_deterministic", False):
        memory_filters = derive_memory_filters(
            state["request"].user_preferences,
            understanding.filters,
            state["request"].message,
        )
        understanding = understanding.model_copy(
            update={"filters": memory_filters.filters}
        )
    output = understanding.model_dump(mode="json")
    if memory_filters is not None:
        output["memory_filters"] = memory_filters.model_dump(mode="json")
    return {
        "query_understanding": understanding.model_dump(mode="python"),
        "warnings": [
            *state.get("warnings", []),
            *understanding.warnings,
            *((memory_filters.warnings if memory_filters else [])),
        ],
        "trace_steps": _append_trace(
            state,
            "query_understanding",
            start_time,
            output,
        ),
    }


async def retrieval_planner_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    plan = build_retrieval_plan(state)
    update = await execute_retrieval_plan(plan, state)
    return {
        **update,
        "trace_steps": _append_trace(
            {**state, **update},
            "retrieval_planner",
            start_time,
            {
                "planned_tasks": [task.task_id for task in plan],
                "evidence_count": len(update.get("evidence_by_id", {})),
                "retrieval_events": update.get("retrieval_events", []),
            },
        ),
    }


async def _run_one_specialist(
    *,
    agent: str,
    runner,
    request,
    assigned_evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
    use_llm_specialists: bool,
    llm_client: GeminiClient | None,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    try:
        if use_llm_specialists and llm_client is not None:
            result = await run_llm_or_deterministic_specialist(
                agent_name=agent,
                deterministic_runner=runner,
                query=request.message,
                evidence=assigned_evidence,
                preferences=preferences,
                readiness=readiness,
                generate_json=llm_client.generate_json,
                timeout_seconds=timeout_seconds,
            )
        else:
            result = await runner(
                query=request.message,
                evidence=assigned_evidence,
                preferences=preferences,
                readiness=readiness,
            )
    except Exception as exc:
        result = {
            "agent_name": agent,
            "status": "failed",
            "content": "",
            "evidence_ids_used": [],
            "sources": [],
            "confidence": "low",
            "warnings": [
                StructuredWarning(
                    code="specialist_error",
                    domain=None,
                    message=f"Specialist {agent} failed.",
                    retryable=True,
                    details={"error": str(exc)},
                )
            ],
            "missing_evidence": [],
        }
    return agent, result


def _blackboard_from_agent_results(
    state: AgentGraphState,
    agent_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "agent_blackboard": state.get("agent_blackboard", {"entries": []})
    }
    working_state = {**state, **update}
    for agent, result in agent_results.items():
        evidence_ids = [str(value) for value in result.get("evidence_ids_used", [])]
        confidence = _normalize_blackboard_confidence(result.get("confidence"))
        update = append_blackboard_entry(
            {**working_state, **update},
            author=agent,
            entry_type="specialist_result",
            content={
                "status": result.get("status"),
                "content": result.get("content", ""),
                "missing_evidence": result.get("missing_evidence", []),
                "warnings": [
                    warning.code if hasattr(warning, "code") else warning
                    for warning in result.get("warnings", [])
                ],
            },
            evidence_ids=evidence_ids,
            confidence=confidence,
            step_name="specialist_agents",
        )
        working_state = {**working_state, **update}
    return update


def _normalize_blackboard_confidence(value: Any) -> str:
    if isinstance(value, str) and value in {"low", "medium", "high"}:
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "medium"
    if numeric >= 0.75:
        return "high"
    if numeric >= 0.45:
        return "medium"
    return "low"


async def specialist_agents_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    request = state["request"]
    settings = get_agent_settings()
    evidence_by_id = state.get("evidence_by_id", {})
    evidence_for_agent = state.get("evidence_for_agent", {})
    runners = {
        "property_search": run_property_agent,
        "project_agent": run_project_agent,
        "market_analysis": run_market_agent,
        "news_agent": run_news_agent,
        "legal_advisor": run_legal_agent,
        "investment_advisor": run_investment_agent,
    }
    use_llm_specialists = (
        settings.AGENT_SPECIALIST_LLM_ENABLED
        and not state.get("force_deterministic", False)
    )
    llm_client = GeminiClient() if use_llm_specialists else None
    specialist_tasks = []
    for agent in state.get("agents_to_run", []):
        runner = runners.get(agent)
        if runner is None:
            continue
        assigned_evidence = [
            evidence_by_id[evidence_id].model_dump(mode="python")
            for evidence_id in evidence_for_agent.get(agent, [])
            if evidence_id in evidence_by_id
        ]
        specialist_tasks.append(
            _run_one_specialist(
                agent=agent,
                runner=runner,
                request=request,
                assigned_evidence=assigned_evidence,
                preferences=request.user_preferences,
                readiness=state.get("readiness", {}),
                use_llm_specialists=use_llm_specialists,
                llm_client=llm_client,
                timeout_seconds=settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
            )
        )

    agent_results = dict(await asyncio.gather(*specialist_tasks)) if specialist_tasks else {}
    blackboard_update = _blackboard_from_agent_results(state, agent_results)
    return {
        "agent_results": agent_results,
        **blackboard_update,
        "trace_steps": _append_trace(
            state,
            "specialist_agents",
            start_time,
            {
                "agents_completed": list(agent_results),
                "blackboard_entries": len(
                    blackboard_update.get("agent_blackboard", {}).get("entries", [])
                ),
            },
        ),
    }


def investment_model_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    if "investment_advisor" not in state.get("agents_to_run", []):
        return {
            "trace_steps": _append_trace(
                state,
                "investment_model",
                start_time,
                {"skipped": True, "reason": "investment_advisor_not_selected"},
            )
        }

    understanding = state.get("query_understanding") or {}
    user_inputs = dict(understanding.get("filters") or {})
    case = build_investment_case(
        evidence_by_id=state.get("evidence_by_id", {}),
        evidence_for_agent=state.get("evidence_for_agent", {}),
    )
    assumptions = resolve_investment_assumptions(
        case=case,
        user_inputs=user_inputs,
        preferences=state["request"].user_preferences,
    )
    metrics = calculate_investment_metrics(
        case=case,
        assumptions=assumptions,
    )
    return {
        "investment_case": case,
        "investment_assumptions": assumptions,
        "investment_metrics": metrics,
        "trace_steps": _append_trace(
            state,
            "investment_model",
            start_time,
            {
                "case_scope": case.get("case_scope"),
                "metric_keys": list(metrics),
                "missing_evidence": case.get("missing_evidence", []),
            },
        ),
    }


def committee_review_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    if "investment_advisor" not in state.get("agents_to_run", []):
        return {
            "trace_steps": _append_trace(
                state,
                "committee_review",
                start_time,
                {"skipped": True, "reason": "investment_advisor_not_selected"},
            )
        }
    review = build_committee_review(
        investment_case=state.get("investment_case", {}),
        investment_assumptions=state.get("investment_assumptions", {}),
        investment_metrics=state.get("investment_metrics", {}),
        agent_blackboard=state.get("agent_blackboard", {}),
        warnings=state.get("warnings", []),
    )
    return {
        "committee_review": review,
        "trace_steps": _append_trace(
            state,
            "committee_review",
            start_time,
            {
                "perspective_count": len(review.get("perspectives", [])),
                "decision": (review.get("recommendation") or {}).get("decision"),
            },
        ),
    }


def _is_evidence_assigned_to_agent(
    *,
    evidence_id: str,
    agent: str,
    evidence: Evidence,
    evidence_for_agent: dict[str, list[str]],
) -> bool:
    return (
        evidence_id in evidence_for_agent.get(agent, [])
        or agent in evidence.assigned_to
    )


def _collect_valid_used_evidence(
    *,
    agent_results: dict[str, dict[str, Any]],
    agents_to_run: list[str],
    evidence_by_id: dict[str, Evidence],
    evidence_for_agent: dict[str, list[str]],
) -> tuple[list[Evidence], list[StructuredWarning], list[str]]:
    valid: list[Evidence] = []
    warnings: list[StructuredWarning] = []
    used_ids: list[str] = []

    for agent in agents_to_run:
        result = agent_results.get(agent) or {}
        for evidence_id in result.get("evidence_ids_used", []):
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                warnings.append(
                    _warning(
                        "invalid_evidence_reference",
                        None,
                        "Specialist referenced an evidence ID that does not exist.",
                        details={"agent": agent, "evidence_id": evidence_id},
                    )
                )
                continue
            if not _is_evidence_assigned_to_agent(
                evidence_id=evidence_id,
                agent=agent,
                evidence=evidence,
                evidence_for_agent=evidence_for_agent,
            ):
                warnings.append(
                    _warning(
                        "invalid_evidence_reference",
                        evidence.domain,
                        "Specialist referenced evidence that was not assigned to it.",
                        details={"agent": agent, "evidence_id": evidence_id},
                    )
                )
                continue
            if evidence_id not in used_ids:
                valid.append(evidence)
                used_ids.append(evidence_id)

    return valid, warnings, used_ids


async def synthesizer_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    agent_results = state.get("agent_results", {})
    parts: list[str] = []
    warnings = list(state.get("warnings", []))

    for agent in state.get("agents_to_run", []):
        result = agent_results.get(agent)
        if not result:
            continue
        content = result.get("content", "")
        if content:
            parts.append(content)
        warnings.extend(result.get("warnings", []))

    evidence_by_id = state.get("evidence_by_id", {})
    evidence_for_agent = state.get("evidence_for_agent", {})
    used_evidence, evidence_warnings, used_evidence_ids = _collect_valid_used_evidence(
        agent_results=agent_results,
        agents_to_run=list(state.get("agents_to_run", [])),
        evidence_by_id=evidence_by_id,
        evidence_for_agent=evidence_for_agent,
    )
    warnings.extend(evidence_warnings)

    sources_by_identity: dict[str, AgentSource] = {}
    for evidence in used_evidence:
        sources_by_identity.setdefault(evidence.source_identity, evidence.source)
    sources = list(sources_by_identity.values())

    warnings = _dedupe_warnings(warnings)
    final_response = "\n\n".join(parts) or "Chua co du thong tin de tra loi yeu cau nay."
    suggested_actions = ["So sanh lua chon", "Hoi them ve phap ly", "Xem xu huong khu vuc"]
    has_committee_review = bool(state.get("committee_review"))
    if has_committee_review:
        final_response = format_investment_scorecard(
            committee_review=state.get("committee_review", {}),
            investment_assumptions=state.get("investment_assumptions", {}),
            investment_metrics=state.get("investment_metrics", {}),
        )
        suggested_actions = [
            "Xac nhan tien thue ky vong",
            "Xac nhan ty le vay va lai suat",
            "Kiem tra phap ly",
        ]
    settings = get_agent_settings()
    use_llm_synthesis = (
        settings.AGENT_SPECIALIST_LLM_ENABLED
        and not state.get("force_deterministic", False)
        and not has_committee_review
    )
    llm_client = GeminiClient() if use_llm_synthesis else None
    synthesis = await synthesize_final_answer(
        query=state["request"].message,
        conversation_context=state.get("compact_context", []),
        agent_results=agent_results,
        deterministic_response=final_response,
        default_actions=suggested_actions,
        generate_json=llm_client.generate_json if llm_client is not None else None,
        timeout_seconds=settings.AGENT_SPECIALIST_LLM_TIMEOUT_SECONDS,
        allowed_evidence_ids=set(used_evidence_ids),
    )
    final_response = synthesis.final_response
    suggested_actions = synthesis.suggested_actions
    warnings = _dedupe_warnings([*warnings, *synthesis.warnings])
    return {
        "final_response": final_response,
        "sources": sources,
        "suggested_actions": suggested_actions,
        "warnings": warnings,
        "trace_steps": _append_trace(
            state,
            "synthesizer",
            start_time,
            {
                "answer_length": len(final_response),
                "source_count": len(sources),
                "used_evidence_ids": used_evidence_ids,
                "used_llm_synthesis": synthesis.used_llm,
            },
        ),
    }

def safety_validator_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    final_response = str(state.get("final_response") or "")
    sources = list(state.get("sources") or [])
    suggested_actions = list(state.get("suggested_actions") or [])
    agents_to_run = list(state.get("agents_to_run") or [])
    warnings = [warning for warning in state.get("warnings") or [] if warning]
    warning_texts = [_warning_text(warning) for warning in warnings]
    normalized_response = _strip_accents(final_response)
    added_warnings: list[str] = []
    agent_results = state.get("agent_results", {})
    evidence_by_id = state.get("evidence_by_id", {})
    evidence_for_agent = state.get("evidence_for_agent", {})
    grounding_fallback_agents: list[str] = []

    if (
        final_response
        and not sources
        and any(agent in SOURCE_BACKED_AGENTS for agent in agents_to_run)
        and not any(warning in NO_SOURCE_WARNINGS for warning in warning_texts)
    ):
        added_warnings.append("final_response_missing_sources")

    if "legal_advisor" in agents_to_run and not any(
        phrase in normalized_response
        for phrase in (
            "tham khao",
            "chuyen gia phap ly",
            "tu van phap ly chuyen nghiep",
        )
    ):
        added_warnings.append("legal_disclaimer_missing")

    if (
        "investment_advisor" in agents_to_run
        and "khong phai loi khuyen tai chinh" not in normalized_response
    ):
        added_warnings.append("financial_disclaimer_missing")

    for agent in agents_to_run:
        result = agent_results.get(agent) or {}
        claims = list(result.get("claims") or [])
        if not claims:
            continue
        valid_ids = _valid_claim_evidence_ids(
            agent=agent,
            evidence_by_id=evidence_by_id,
            evidence_for_agent=evidence_for_agent,
        )
        if _invalid_claim_ratio(claims, valid_ids) > 0.0:
            grounding_fallback_agents.append(agent)
            added_warnings.append("agent_answer_missing_valid_evidence")

    if grounding_fallback_agents:
        final_response = _response_with_grounding_fallbacks(
            agents_to_run=agents_to_run,
            agent_results=agent_results,
            fallback_agents=set(grounding_fallback_agents),
            current_response=final_response,
        )

    warnings = _dedupe_warnings([*warnings, *added_warnings])
    return {
        "final_response": final_response,
        "sources": sources,
        "suggested_actions": suggested_actions,
        "warnings": warnings,
        "trace_steps": _append_trace(
            state,
            "safety_validator",
            start_time,
            {
                "warning_count": len(warnings),
                "added_warnings": added_warnings,
                "grounding_fallback_agents": grounding_fallback_agents,
            },
        ),
    }


def memory_proposal_node(state: AgentGraphState) -> AgentGraphState:
    start_time = time.perf_counter()
    understanding = state.get("query_understanding") or {}
    filters = understanding.get("filters") or {}
    memory_proposals = extract_memory_proposals(
        query=state["request"].message,
        filters=filters,
    )

    return {
        "memory_proposals": memory_proposals,
        "trace_steps": _append_trace(
            state,
            "memory_proposals",
            start_time,
            {"proposal_count": len(memory_proposals)},
        ),
    }
