from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.models.agent_observability import (
    AgentRetrievalEvent,
    AgentTrace,
    AgentTraceStep,
    EvalRun,
)
from app.models.chat import ChatSession
from app.models.user import User
from app.services.agent_service.contracts import AgentChatResponse, StructuredWarning


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _truncate_json(value: Any, max_chars: int = 16384) -> Any:
    safe_value = _jsonable(value)
    try:
        encoded = json.dumps(safe_value, ensure_ascii=True, default=str)
    except TypeError:
        encoded = json.dumps(str(safe_value), ensure_ascii=True)

    if len(encoded) <= max_chars:
        return safe_value
    return {
        "truncated": True,
        "truncated_json": encoded[:max_chars],
        "original_length": len(encoded),
    }


def _trace_summary_dict(response: AgentChatResponse) -> dict[str, Any]:
    return response.trace_summary.model_dump(mode="json")


def _warning_text(warning: Any) -> str | None:
    if isinstance(warning, StructuredWarning):
        return warning.message
    if isinstance(warning, dict):
        return warning.get("message") or warning.get("code") or str(warning)
    if warning is None:
        return None
    return str(warning)


def _status(response: AgentChatResponse) -> str:
    mode = response.full_trace.get("mode") if isinstance(response.full_trace, dict) else None
    if mode in {"agent_service_error", "failure"}:
        return "error"
    if "agent_service_error" in response.agents_used:
        return "error"
    if response.trace_summary.intent in {"agent_service_error", "failure"}:
        return "error"
    if response.trace_summary.warnings:
        return "partial"
    return "success"


def _error_message(response: AgentChatResponse) -> str | None:
    mode = response.full_trace.get("mode") if isinstance(response.full_trace, dict) else None
    if mode in {"agent_service_error", "failure"}:
        warnings = [_warning_text(warning) for warning in response.trace_summary.warnings]
        return next((warning for warning in warnings if warning), None)
    error = response.full_trace.get("error") if isinstance(response.full_trace, dict) else None
    if isinstance(error, dict):
        return error.get("message") or error.get("error_message") or str(error)
    if error:
        return str(error)
    return None


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _steps(full_trace: dict[str, Any]) -> list[dict[str, Any]]:
    steps = full_trace.get("steps", [])
    if not isinstance(steps, list):
        return []
    return [step for step in steps if isinstance(step, dict)]


def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    for key in (
        "task_id",
        "domain",
        "warning",
        "warnings",
        "skip_reason",
        "retrieved_for",
        "depends_on",
        "dependency_mode",
        "error",
    ):
        if key in event and key not in metadata:
            metadata[key] = event[key]
    return _truncate_json(metadata)


def _retrieval_events_from_steps(steps: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for step in steps:
        output = step.get("output")
        if not isinstance(output, dict):
            continue
        step_events = output.get("retrieval_events", [])
        if isinstance(step_events, list):
            events.extend(event for event in step_events if isinstance(event, dict))
    return events


def _retrieval_plan_by_id(full_trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    plan = full_trace.get("retrieval_plan", [])
    if not isinstance(plan, list):
        return {}
    return {
        str(task["task_id"]): task
        for task in plan
        if isinstance(task, dict) and task.get("task_id")
    }


def _retrieval_result_event(
    task_id: str,
    result: dict[str, Any],
    task: dict[str, Any] | None,
) -> dict[str, Any]:
    event = dict(result)
    event["task_id"] = event.get("task_id") or task_id
    if task:
        for key in (
            "tool",
            "domain",
            "filters",
            "retrieved_for",
            "depends_on",
            "dependency_mode",
        ):
            if key not in event and key in task:
                event[key] = task[key]
    return event


def _fallback_retrieval_events(full_trace: dict[str, Any]) -> list[dict[str, Any]]:
    fallback = full_trace.get("retrieval_results", [])
    if isinstance(fallback, list):
        return [event for event in fallback if isinstance(event, dict)]
    if not isinstance(fallback, dict):
        return []

    plan_by_id = _retrieval_plan_by_id(full_trace)
    events = []
    for task_id, result in fallback.items():
        if isinstance(result, dict):
            events.append(
                _retrieval_result_event(
                    str(task_id),
                    result,
                    plan_by_id.get(str(task_id)),
                )
            )
    return events


def _retrieval_events(full_trace: dict[str, Any], steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events = _retrieval_events_from_steps(steps)
    events.extend(_fallback_retrieval_events(full_trace))
    return events


def _tool_name(event: dict[str, Any]) -> str:
    return (
        event.get("tool_name")
        or event.get("tool")
        or event.get("retriever")
        or "unknown"
    )


def _result_count(event: dict[str, Any]) -> int:
    if "result_count" in event:
        return _safe_int(event.get("result_count"))
    if isinstance(event.get("results"), list):
        return len(event["results"])
    if isinstance(event.get("evidence_ids"), list):
        return len(event["evidence_ids"])
    return 0


def _event_latency_ms(event: dict[str, Any]) -> float:
    if "latency_ms" in event:
        return _safe_float(event.get("latency_ms"))
    return _safe_float(event.get("duration_ms"))


async def persist_agent_observability(
    *,
    session_factory,
    chat_session: ChatSession,
    user: User | None,
    response: AgentChatResponse,
) -> None:
    request_id = response.request_id
    full_trace = response.full_trace if isinstance(response.full_trace, dict) else {}
    trace_steps = _steps(full_trace)

    async with session_factory() as db:
        result = await db.execute(
            select(AgentTrace).where(AgentTrace.request_id == request_id)
        )
        trace = result.scalar_one_or_none()
        if trace is None:
            trace = AgentTrace(request_id=request_id)
            db.add(trace)

        trace.session_id = chat_session.id
        trace.user_id = user.id if user else None
        trace.intent = response.trace_summary.intent
        trace.agents_used = _truncate_json(response.agents_used)
        trace.trace_summary_json = _truncate_json(_trace_summary_dict(response))
        trace.full_trace_json = _truncate_json(full_trace)
        trace.readiness_json = _truncate_json(response.readiness)
        trace.latency_ms = _safe_float(response.trace_summary.latency_ms)
        trace.status = _status(response)
        trace.error_message = _error_message(response)
        trace.graph_version = full_trace.get("graph_version")
        trace.prompt_version = full_trace.get("prompt_version")
        trace.model_name = full_trace.get("model_name")

        await db.execute(
            delete(AgentTraceStep).where(AgentTraceStep.request_id == request_id)
        )
        for step in trace_steps:
            db.add(
                AgentTraceStep(
                    request_id=request_id,
                    step_name=step.get("step_name") or "unknown",
                    status=step.get("status") or "success",
                    latency_ms=_safe_float(step.get("latency_ms")),
                    input_json=_truncate_json(step.get("input", {}), 4096),
                    output_json=_truncate_json(step.get("output", {})),
                    error_message=step.get("error_message"),
                )
            )

        await db.execute(
            delete(AgentRetrievalEvent).where(
                AgentRetrievalEvent.request_id == request_id
            )
        )
        for event in _retrieval_events(full_trace, trace_steps):
            db.add(
                AgentRetrievalEvent(
                    request_id=request_id,
                    tool_name=_tool_name(event),
                    parent_type=event.get("parent_type") or event.get("source_type"),
                    filters_json=_truncate_json(event.get("filters", {})),
                    result_count=_result_count(event),
                    latency_ms=_event_latency_ms(event),
                    status=event.get("status") or "success",
                    error_message=event.get("error_message")
                    or event.get("skip_reason")
                    or (
                        event.get("error", {}).get("message")
                        if isinstance(event.get("error"), dict)
                        else None
                    ),
                    metadata_json=_event_metadata(event),
                )
            )

        await db.commit()


async def mark_stale_eval_runs_failed(db) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=10)
    result = await db.execute(
        select(EvalRun).where(
            EvalRun.status == "pending",
            EvalRun.created_at < cutoff,
        )
    )
    runs = result.scalars().all()
    for run in runs:
        run.status = "failed"
        run.error_message = "eval_timeout_stale"
        run.completed_at = datetime.utcnow()
    if runs:
        await db.commit()
    return len(runs)
