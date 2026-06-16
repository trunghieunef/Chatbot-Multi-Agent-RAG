from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Confidence = Literal["low", "medium", "high"]


class BlackboardEntry(BaseModel):
    id: str
    author: str
    type: str
    content: dict[str, Any] | str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    created_at_step: str


def _existing_evidence_ids(state: dict[str, Any]) -> set[str]:
    return set((state.get("evidence_by_id") or {}).keys())


def _next_entry_id(entries: list[dict[str, Any]], author: str) -> str:
    safe_author = author.replace(" ", "_")
    return f"bb_{safe_author}_{len(entries) + 1}"


def append_blackboard_entry(
    state: dict[str, Any],
    *,
    author: str,
    entry_type: str,
    content: dict[str, Any] | str,
    evidence_ids: list[str],
    confidence: Confidence,
    step_name: str,
) -> dict[str, Any]:
    blackboard = dict(state.get("agent_blackboard") or {})
    entries = [dict(entry) for entry in blackboard.get("entries", [])]
    valid_ids = _existing_evidence_ids(state)
    clean_evidence_ids = [
        evidence_id
        for evidence_id in evidence_ids
        if evidence_id in valid_ids
    ]
    entry = BlackboardEntry(
        id=_next_entry_id(entries, author),
        author=author,
        type=entry_type,
        content=content,
        evidence_ids=list(dict.fromkeys(clean_evidence_ids)),
        confidence=confidence,
        created_at_step=step_name,
    )
    entries.append(entry.model_dump(mode="python"))
    blackboard["entries"] = entries
    return {"agent_blackboard": blackboard}


def entries_by_author(
    blackboard: dict[str, Any],
    author: str,
) -> list[dict[str, Any]]:
    return [
        dict(entry)
        for entry in blackboard.get("entries", [])
        if entry.get("author") == author
    ]
