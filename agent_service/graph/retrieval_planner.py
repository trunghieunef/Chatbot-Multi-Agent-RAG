from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from typing import Any

from agent_service.contracts import (
    AgentSource,
    Evidence,
    MatchedChunk,
    RetrievalResult,
    RetrievalTask,
    StructuredWarning,
)
from agent_service.graph.state import AgentGraphState
from agent_service.tools.retrieval import RetrievalTrace, _run_hybrid_tool


DOMAIN_SOURCE = {
    "property": "listings",
    "project": "projects",
    "news": "news",
    "legal": "legal",
    "market": "listings",
}


def _strip_accents(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    ).lower()


def _extract_filters(query: str) -> dict[str, Any]:
    normalized = _strip_accents(query)
    filters: dict[str, Any] = {}

    if any(term in normalized for term in ("thue", "cho thue")):
        filters["listing_type"] = "rent"
    elif any(term in normalized for term in ("tim", "mua", "ban", "dau tu")):
        filters["listing_type"] = "sale"

    if "can ho" in normalized or "chung cu" in normalized:
        filters["property_type"] = "Can ho"

    if any(
        term in normalized
        for term in ("ho chi minh", "tp hcm", "tphcm", "sai gon", "saigon")
    ):
        filters["city"] = "Ho Chi Minh"

    district_match = re.search(r"\b(?:quan|q)\s*(\d{1,2})\b", normalized)
    if district_match:
        filters["district"] = f"Quan {district_match.group(1)}"

    max_price_match = re.search(
        r"(?:duoi|toi da|khong qua)\s*(\d+(?:[\.,]\d+)?)\s*(?:ty|ti)",
        normalized,
    )
    if max_price_match:
        filters["max_price"] = float(max_price_match.group(1).replace(",", "."))

    return filters


def readiness_capabilities(readiness: dict[str, Any]) -> dict[str, dict[str, bool]]:
    capabilities: dict[str, dict[str, bool]] = {}
    for domain, source_name in DOMAIN_SOURCE.items():
        source = readiness.get(source_name, {})
        if isinstance(source, dict):
            parent_count = int(source.get("parent_count") or 0)
            chunk_count = int(source.get("chunk_count") or 0)
        else:
            parent_count = 0
            chunk_count = 0

        capabilities[domain] = {
            "parent_ready": parent_count > 0,
            "structured_search_ready": parent_count > 0,
            "semantic_index_ready": parent_count > 0 and chunk_count > 0,
            "market_aggregate_ready": parent_count > 0 and domain in {"property", "market"},
        }
    return capabilities


def _needs_project(query: str) -> bool:
    normalized = _strip_accents(query)
    return any(term in normalized for term in ("du an", "chu dau tu", "ha tang"))


def _needs_news(query: str) -> bool:
    normalized = _strip_accents(query)
    return any(
        term in normalized
        for term in ("tin tuc", "bien dong", "cap nhat", "thi truong gan day")
    )


def _location_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in filters.items()
        if key in {"district", "city"}
    }


def build_retrieval_plan(state: AgentGraphState) -> list[RetrievalTask]:
    request = state["request"]
    agents = list(state.get("agents_to_run", []))
    caps = readiness_capabilities(state.get("readiness", {}))
    understanding = state.get("query_understanding") or {}
    query = understanding.get("rewritten_query") or request.message
    listing_filters = understanding.get("filters") or _extract_filters(request.message)
    plan: list[RetrievalTask] = []

    if "property_search" in agents and caps["property"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_property_1",
                domain="property",
                tool="search_listings",
                query=query,
                filters=listing_filters,
                retrieved_for=["property_search"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    if (
        "investment_advisor" in agents
        and caps["market"]["market_aggregate_ready"]
        and listing_filters.get("city")
    ):
        plan.append(
            RetrievalTask(
                task_id="market_lookup_1",
                domain="market",
                tool="lookup_market_metrics",
                query=query,
                filters=listing_filters,
                retrieved_for=["investment_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=10,
                rerank_top_k=None,
            )
        )

    if "legal_advisor" in agents and caps["legal"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_legal_1",
                domain="legal",
                tool="search_articles",
                query=query,
                filters={"category": "legal"},
                retrieved_for=["legal_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    if "project_agent" in agents and caps["project"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_project_1",
                domain="project",
                tool="search_projects",
                query=query,
                filters=_location_filters(listing_filters),
                retrieved_for=["project_agent"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    should_search_news = "news_agent" in agents or (
        "investment_advisor" in agents and _needs_news(query)
    )
    if should_search_news and caps["news"]["semantic_index_ready"]:
        plan.append(
            RetrievalTask(
                task_id="search_news_1",
                domain="news",
                tool="search_articles",
                query=query,
                filters={"exclude_category": "legal"},
                retrieved_for=[
                    "news_agent" if "news_agent" in agents else "investment_advisor"
                ],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    should_search_project_for_investment = (
        "investment_advisor" in agents
        and "project_agent" not in agents
        and _needs_project(query)
        and caps["project"]["semantic_index_ready"]
    )
    if should_search_project_for_investment:
        plan.append(
            RetrievalTask(
                task_id="search_project_for_investment_1",
                domain="project",
                tool="search_projects",
                query=query,
                filters=_location_filters(listing_filters),
                retrieved_for=["investment_advisor"],
                depends_on=[],
                dependency_mode="none",
                top_k=20,
                rerank_top_k=5,
            )
        )

    return plan


def structured_warning(
    *,
    code: str,
    domain: str | None,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> StructuredWarning:
    return StructuredWarning(
        code=code,
        domain=domain,
        message=message,
        retryable=retryable,
        details=details or {},
    )


def _stable_source_identity(
    domain: str,
    source_type: str,
    record: dict[str, Any],
) -> str:
    if source_type == "listing":
        key = record.get("product_id") or record.get("id")
    elif source_type == "project":
        key = record.get("slug") or record.get("url") or record.get("id")
    elif source_type == "article":
        key = record.get("url") or record.get("id")
    else:
        key = record.get("source_identity") or record.get("id") or domain
    return f"{source_type}:{key}"


def _location_fact(record: dict[str, Any]) -> dict[str, Any] | None:
    location = {
        "ward": record.get("ward"),
        "district": record.get("district"),
        "city": record.get("city"),
        "address": record.get("address") or record.get("location"),
    }
    clean = {key: value for key, value in location.items() if value}
    return clean or None


def _score_from_chunk(raw_chunk: dict[str, Any]) -> tuple[float | None, float | None]:
    rerank_score = _optional_float(raw_chunk.get("rerank_score"))
    if rerank_score is not None:
        return rerank_score, rerank_score
    return None, None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _matched_chunks_from_record(record: dict[str, Any]) -> list[MatchedChunk]:
    raw_chunks = record.get("matched_chunks")
    if not raw_chunks and record.get("matched_chunk"):
        raw_chunks = [record["matched_chunk"]]

    chunks: list[MatchedChunk] = []
    for index, raw_chunk in enumerate(raw_chunks or []):
        if not isinstance(raw_chunk, dict):
            continue
        rerank_score, final_score = _score_from_chunk(raw_chunk)
        chunks.append(
            MatchedChunk(
                id=str(raw_chunk.get("id") or f"chunk:{index}"),
                chunk_type=raw_chunk.get("chunk_type"),
                text=raw_chunk.get("text"),
                vector_distance=_optional_float(raw_chunk.get("distance")),
                semantic_score=None,
                rerank_score=rerank_score,
                final_score=final_score,
            )
        )
    return chunks


def _source_from_normalized(
    *,
    domain: str,
    source_type: str,
    source_identity: str,
    record: dict[str, Any],
    chunks: list[MatchedChunk],
) -> AgentSource:
    title = record.get("title") or record.get("name")
    snippet = next((chunk.text for chunk in chunks if chunk.text), None)
    score = next(
        (chunk.final_score for chunk in chunks if chunk.final_score is not None),
        None,
    )
    return AgentSource(
        type=source_type,
        domain=domain,
        id=source_identity,
        product_id=record.get("product_id"),
        title=title,
        url=record.get("url"),
        snippet=snippet,
        location=_location_fact(record),
        citation=record.get("citation"),
        score=score,
        metadata={
            key: value
            for key, value in {
                "source_identity": source_identity,
                "price_text": record.get("price_text") or record.get("price_range"),
                "area_text": record.get("area_text") or record.get("area_range"),
                "category": record.get("category"),
            }.items()
            if value is not None
        },
    )


def _facts_from_record(
    domain: str,
    source_type: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    facts = {
        "title": record.get("title") or record.get("name"),
        "price": record.get("price"),
        "price_text": record.get("price_text") or record.get("price_range"),
        "area": record.get("area"),
        "area_text": record.get("area_text") or record.get("area_range"),
        "price_per_m2": record.get("price_per_m2"),
        "location": _location_fact(record),
        "category": record.get("category"),
        "legal_status_claimed": record.get("legal_status"),
    }
    return {key: value for key, value in facts.items() if value is not None}


def normalize_record_to_evidence(
    *,
    record: dict[str, Any],
    task: RetrievalTask,
    evidence_index: int,
    assigned_to: list[str],
) -> Evidence:
    if task.domain == "market":
        source_identity = str(
            record.get("source_identity") or f"market:{evidence_index}"
        )
        source = AgentSource(
            type="market_metric",
            domain="market",
            id=source_identity,
            title=str(record.get("metric") or "Market metric"),
            url=None,
            snippet=(
                f"{record.get('metric')}: {record.get('value')} "
                f"{record.get('unit')}"
            ),
            location=record.get("location"),
            score=None,
            metadata={
                key: value
                for key, value in {
                    "source_identity": source_identity,
                    "metric": record.get("metric"),
                    "period": record.get("period"),
                }.items()
                if value is not None
            },
        )
        return Evidence(
            evidence_id=f"ev_{task.task_id}_{evidence_index}",
            retrieval_task_id=task.task_id,
            domain="market",
            source_type="market_metric",
            source_identity=source_identity,
            record=record,
            facts={
                key: value
                for key, value in {
                    "metric": record.get("metric"),
                    "value": record.get("value"),
                    "unit": record.get("unit"),
                    "location": record.get("location"),
                    "property_type": record.get("property_type"),
                    "period": record.get("period"),
                }.items()
                if value is not None
            },
            source=source,
            matched_chunks=[],
            retrieved_for=task.retrieved_for,
            assigned_to=assigned_to,
            warnings=[],
        )

    source_type = {
        "property": "listing",
        "project": "project",
        "news": "article",
        "legal": "article",
        "market": "market_metric",
    }[task.domain]
    source_identity = _stable_source_identity(task.domain, source_type, record)
    chunks = _matched_chunks_from_record(record)
    source = _source_from_normalized(
        domain=task.domain,
        source_type=source_type,
        source_identity=source_identity,
        record=record,
        chunks=chunks,
    )
    return Evidence(
        evidence_id=f"ev_{task.task_id}_{evidence_index}",
        retrieval_task_id=task.task_id,
        domain=task.domain,
        source_type=source_type,
        source_identity=source_identity,
        record=record,
        facts=_facts_from_record(task.domain, source_type, record),
        source=source,
        matched_chunks=chunks,
        retrieved_for=task.retrieved_for,
        assigned_to=assigned_to,
        warnings=[],
    )


def _assigned_agents_for_task(
    task: RetrievalTask,
    agents_to_run: list[str],
) -> list[str]:
    assigned = list(task.retrieved_for)
    if task.domain == "property" and "investment_advisor" in agents_to_run:
        assigned.append("investment_advisor")
    if task.domain in {"project", "news", "market"} and "investment_advisor" in agents_to_run:
        assigned.append("investment_advisor")
    return list(dict.fromkeys(assigned))


def _parent_type_for_task(task: RetrievalTask) -> str:
    return {
        "property": "listing",
        "project": "project",
        "news": "article",
        "legal": "article",
    }[task.domain]


async def _execute_single_retrieval_task(
    *,
    task: RetrievalTask,
    request: Any,
    agents_to_run: list[str],
) -> tuple[
    RetrievalTask,
    RetrievalResult,
    list[Evidence],
    list[StructuredWarning],
    list[dict[str, Any]],
]:
    task_started = time.perf_counter()
    trace_events: list[dict[str, Any]] = [
        {"event": "retrieval_task_started", "task_id": task.task_id}
    ]
    warnings: list[StructuredWarning] = []
    evidence_items: list[Evidence] = []

    try:
        if task.domain == "market":
            from agent_service.tools.market import lookup_market_metrics

            records = await lookup_market_metrics(task.filters)
            if not records:
                warning = structured_warning(
                    code="investment_market_data_missing",
                    domain="market",
                    message="Market aggregate evidence is not available for this query.",
                    retryable=False,
                    details={"task_id": task.task_id, "filters": task.filters},
                )
                warnings.append(warning)
                result = RetrievalResult(
                    task_id=task.task_id,
                    status="skipped",
                    evidence_ids=[],
                    duration_ms=round((time.perf_counter() - task_started) * 1000),
                    warnings=[warning],
                    skip_reason="investment_market_data_missing",
                )
                trace_events.append(
                    {"event": "retrieval_task_skipped", "task_id": task.task_id}
                )
                return task, result, evidence_items, warnings, trace_events
        else:
            trace = RetrievalTrace(request_id=request.request_id)
            records = await _run_hybrid_tool(
                query=task.query,
                filters=task.filters,
                trace=trace,
                tool_name=task.tool,
                parent_type=_parent_type_for_task(task),
                top_k=task.top_k,
                rerank_to=task.rerank_top_k or task.top_k,
            )
    except Exception as exc:
        warning = structured_warning(
            code="retrieval_error",
            domain=task.domain,
            message=f"Retrieval task {task.task_id} failed.",
            retryable=True,
            details={"error": str(exc)},
        )
        warnings.append(warning)
        result = RetrievalResult(
            task_id=task.task_id,
            status="failed",
            evidence_ids=[],
            duration_ms=round((time.perf_counter() - task_started) * 1000),
            warnings=[warning],
            error={"type": exc.__class__.__name__, "message": str(exc)},
        )
        trace_events.append({"event": "retrieval_task_failed", "task_id": task.task_id})
        return task, result, evidence_items, warnings, trace_events

    if not records:
        warning = structured_warning(
            code="no_evidence",
            domain=task.domain,
            message=f"No evidence found for {task.domain}.",
            retryable=False,
            details={"task_id": task.task_id},
        )
        warnings.append(warning)
        result = RetrievalResult(
            task_id=task.task_id,
            status="empty",
            evidence_ids=[],
            duration_ms=round((time.perf_counter() - task_started) * 1000),
            warnings=[warning],
        )
        trace_events.append({"event": "retrieval_task_empty", "task_id": task.task_id})
        return task, result, evidence_items, warnings, trace_events

    assigned_to = _assigned_agents_for_task(task, agents_to_run)
    evidence_ids: list[str] = []
    for index, record in enumerate(records, start=1):
        evidence = normalize_record_to_evidence(
            record=record,
            task=task,
            evidence_index=index,
            assigned_to=assigned_to,
        )
        evidence_items.append(evidence)
        evidence_ids.append(evidence.evidence_id)

    result = RetrievalResult(
        task_id=task.task_id,
        status="completed",
        evidence_ids=evidence_ids,
        duration_ms=round((time.perf_counter() - task_started) * 1000),
        warnings=[],
    )
    trace_events.append(
        {
            "event": "retrieval_task_completed",
            "task_id": task.task_id,
            "evidence_ids": evidence_ids,
        }
    )
    trace_events.append(
        {
            "event": "evidence_assigned",
            "task_id": task.task_id,
            "assigned_to": assigned_to,
            "evidence_ids": evidence_ids,
        }
    )
    return task, result, evidence_items, warnings, trace_events


async def execute_retrieval_plan(
    plan: list[RetrievalTask],
    state: AgentGraphState,
) -> dict[str, Any]:
    started_all = time.perf_counter()
    request = state["request"]
    agents_to_run = list(state.get("agents_to_run", []))
    evidence_by_id: dict[str, Evidence] = {}
    evidence_for_agent: dict[str, list[str]] = {agent: [] for agent in agents_to_run}
    retrieval_results: dict[str, RetrievalResult] = {}
    warnings: list[StructuredWarning] = []
    trace_events: list[dict[str, Any]] = [
        {
            "event": "retrieval_plan_created",
            "task_count": len(plan),
            "task_ids": [task.task_id for task in plan],
        }
    ]

    task_outputs = await asyncio.gather(
        *(
            _execute_single_retrieval_task(
                task=task,
                request=request,
                agents_to_run=agents_to_run,
            )
            for task in plan
        )
    )

    for task, result, evidence_items, task_warnings, task_events in task_outputs:
        retrieval_results[task.task_id] = result
        warnings.extend(task_warnings)
        trace_events.extend(task_events)
        for evidence in evidence_items:
            evidence_by_id[evidence.evidence_id] = evidence
            for agent in evidence.assigned_to:
                evidence_for_agent.setdefault(agent, []).append(evidence.evidence_id)

    return {
        "retrieval_plan": plan,
        "retrieval_results": retrieval_results,
        "evidence_by_id": evidence_by_id,
        "evidence_for_agent": evidence_for_agent,
        "retrieval_events": trace_events,
        "warnings": [*state.get("warnings", []), *warnings],
        "retrieval_duration_ms": round((time.perf_counter() - started_all) * 1000),
    }

