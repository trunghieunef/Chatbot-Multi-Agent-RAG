from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError


GenerateJson = Callable[..., Awaitable[dict[str, Any]]]


class SynthesisPayload(BaseModel):
    final_response: str
    suggested_actions: list[str] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids_used: list[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    final_response: str
    suggested_actions: list[str]
    warnings: list[Any] = Field(default_factory=list)
    used_llm: bool = False


def build_synthesis_prompt(
    *,
    query: str,
    conversation_context: list[dict[str, Any]],
    agent_results: dict[str, dict[str, Any]],
) -> str:
    compact_results = {
        agent: {
            "status": result.get("status"),
            "content": result.get("content"),
            "evidence_ids_used": result.get("evidence_ids_used", []),
            "warnings": [
                warning.code if hasattr(warning, "code") else warning
                for warning in result.get("warnings", [])
            ],
        }
        for agent, result in agent_results.items()
    }
    return "\n".join(
        [
            "You are the final response synthesizer for a Vietnamese real-estate assistant.",
            (
                "Return JSON only with final_response, suggested_actions, claims, "
                "and evidence_ids_used."
            ),
            "Use only the agent outputs and evidence IDs provided.",
            "Do not invent listings, prices, laws, market facts, or citations.",
            "Every factual claim must include evidence_ids from the provided agent outputs.",
            "If evidence is missing, say what is missing and ask a useful follow-up.",
            f"User query: {query}",
            f"Conversation context: {json.dumps(conversation_context, ensure_ascii=True)}",
            f"Agent results: {json.dumps(compact_results, ensure_ascii=True, default=str)}",
        ]
    )


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


def _invalid_grounding_warning(
    payload: SynthesisPayload,
    allowed_evidence_ids: set[str] | None,
) -> str | None:
    if allowed_evidence_ids is None:
        return None

    evidence_claims = [
        claim for claim in payload.claims if _claim_requires_evidence(claim)
    ]
    if not allowed_evidence_ids:
        if payload.claims and not evidence_claims and not payload.evidence_ids_used:
            return None
        return "synthesizer_missing_allowed_evidence"

    if not evidence_claims:
        return "synthesizer_missing_claims"

    used_ids = {str(evidence_id) for evidence_id in payload.evidence_ids_used}
    if not used_ids:
        return "synthesizer_missing_evidence_ids"
    if not used_ids.issubset(allowed_evidence_ids):
        return "synthesizer_invalid_evidence"

    for claim in evidence_claims:
        claim_ids = _claim_evidence_ids(claim)
        if not claim_ids or not claim_ids.issubset(allowed_evidence_ids):
            return "synthesizer_invalid_evidence"

    return None


async def synthesize_final_answer(
    *,
    query: str,
    conversation_context: list[dict[str, Any]],
    agent_results: dict[str, dict[str, Any]],
    deterministic_response: str,
    default_actions: list[str],
    generate_json: GenerateJson | None,
    timeout_seconds: float,
    allowed_evidence_ids: set[str] | None = None,
) -> SynthesisResult:
    if generate_json is None:
        return SynthesisResult(
            final_response=deterministic_response,
            suggested_actions=default_actions,
            warnings=[],
            used_llm=False,
        )

    try:
        payload = await generate_json(
            build_synthesis_prompt(
                query=query,
                conversation_context=conversation_context,
                agent_results=agent_results,
            ),
            timeout_seconds=timeout_seconds,
        )
        parsed = SynthesisPayload.model_validate(payload)
    except (TypeError, ValueError, ValidationError):
        return SynthesisResult(
            final_response=deterministic_response,
            suggested_actions=default_actions,
            warnings=["synthesizer_invalid_json"],
            used_llm=False,
        )

    final_response = parsed.final_response.strip()
    if not final_response:
        return SynthesisResult(
            final_response=deterministic_response,
            suggested_actions=default_actions,
            warnings=["synthesizer_empty_response"],
            used_llm=False,
        )

    invalid_grounding = _invalid_grounding_warning(
        parsed,
        (
            {str(evidence_id) for evidence_id in allowed_evidence_ids}
            if allowed_evidence_ids is not None
            else None
        ),
    )
    if invalid_grounding is not None:
        return SynthesisResult(
            final_response=deterministic_response,
            suggested_actions=default_actions,
            warnings=[invalid_grounding],
            used_llm=False,
        )

    return SynthesisResult(
        final_response=final_response,
        suggested_actions=parsed.suggested_actions or default_actions,
        warnings=[],
        used_llm=True,
    )
