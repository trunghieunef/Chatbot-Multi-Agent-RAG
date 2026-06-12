from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError


DeterministicRunner = Callable[..., Awaitable[dict[str, Any]]]
GenerateJson = Callable[..., Awaitable[dict[str, Any]]]


class LLMSpecialistOutput(BaseModel):
    agent_name: str
    status: str
    content: str
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids_used: list[str] = Field(default_factory=list)
    confidence: float | str | None = None
    warnings: list[Any] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


def _evidence_id(record: dict[str, Any]) -> str | None:
    value = record.get("evidence_id") or record.get("id")
    return str(value) if value is not None else None


def _compact_evidence(record: dict[str, Any]) -> dict[str, Any]:
    facts = record.get("facts") if isinstance(record.get("facts"), dict) else {}
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    return {
        "evidence_id": _evidence_id(record),
        "domain": record.get("domain"),
        "source_type": record.get("source_type"),
        "facts": facts,
        "source": {
            "type": source.get("type"),
            "title": source.get("title"),
            "url": source.get("url"),
        },
    }


def build_specialist_prompt(
    *,
    agent_name: str,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
) -> str:
    evidence_payload = [_compact_evidence(record) for record in evidence]
    return "\n".join(
        [
            "You are a real-estate specialist agent. Return JSON only.",
            f"Agent name: {agent_name}",
            f"User query: {query}",
            f"User preferences: {json.dumps(preferences, ensure_ascii=True)}",
            "Use only the provided evidence IDs. Do not cite or infer from unseen evidence.",
            "If evidence is insufficient, return status no_evidence or partial and explain what is missing.",
            "Required JSON fields: agent_name, status, content, claims, evidence_ids_used, confidence, warnings, missing_evidence.",
            "Each claim should include text and evidence_id when it depends on a source.",
            f"Evidence: {json.dumps(evidence_payload, ensure_ascii=True)}",
        ]
    )


def _append_warning(result: dict[str, Any], warning: str) -> dict[str, Any]:
    updated = dict(result)
    updated["warnings"] = [*list(updated.get("warnings") or []), warning]
    return updated


def _valid_evidence_ids(evidence: list[dict[str, Any]]) -> set[str]:
    return {
        evidence_id
        for record in evidence
        if (evidence_id := _evidence_id(record)) is not None
    }


def _requires_source_claims(
    output: LLMSpecialistOutput,
    evidence: list[dict[str, Any]],
) -> bool:
    return (
        output.status in {"completed", "partial"}
        and bool(output.content.strip())
        and bool(_valid_evidence_ids(evidence))
    )


async def run_llm_or_deterministic_specialist(
    *,
    agent_name: str,
    deterministic_runner: DeterministicRunner,
    query: str,
    evidence: list[dict[str, Any]],
    preferences: dict[str, Any],
    readiness: dict[str, Any],
    generate_json: GenerateJson,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    deterministic_result = await deterministic_runner(
        query=query,
        evidence=evidence,
        preferences=preferences,
        readiness=readiness,
    )

    try:
        prompt = build_specialist_prompt(
            agent_name=agent_name,
            query=query,
            evidence=evidence,
            preferences=preferences,
        )
        try:
            payload = await generate_json(prompt, timeout_seconds=timeout_seconds)
        except TypeError:
            payload = await generate_json(prompt)
        output = LLMSpecialistOutput.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        return _append_warning(deterministic_result, "llm_specialist_invalid_json")

    if output.agent_name != agent_name:
        return _append_warning(deterministic_result, "llm_specialist_invalid_json")

    if _requires_source_claims(output, evidence) and not output.claims:
        return _append_warning(deterministic_result, "llm_specialist_missing_claims")

    allowed_ids = _valid_evidence_ids(evidence)
    used_ids = {str(evidence_id) for evidence_id in output.evidence_ids_used}
    if not used_ids.issubset(allowed_ids):
        return _append_warning(deterministic_result, "llm_specialist_invalid_evidence")

    result = output.model_dump(mode="python")
    result["fallback_content"] = deterministic_result.get("content", "")
    return result
