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


def read_blackboard(
    state: dict[str, Any],
    *,
    author: str | None = None,
    entry_type: str | None = None,
    min_confidence: Confidence = "low",
    max_entries: int = 10,
) -> list[dict[str, Any]]:
    """Read entries from the blackboard, optionally filtered.

    Agents use this to discover what other agents have found.
    """
    blackboard = state.get("agent_blackboard") or {}
    entries = blackboard.get("entries", [])

    confidence_order: dict[Confidence, int] = {"low": 0, "medium": 1, "high": 2}
    min_level = confidence_order.get(min_confidence, 0)

    filtered: list[dict[str, Any]] = []
    for entry in entries:
        if author is not None and entry.get("author") != author:
            continue
        if entry_type is not None and entry.get("type") != entry_type:
            continue
        entry_conf = entry.get("confidence", "low")
        if confidence_order.get(entry_conf, 0) < min_level:
            continue
        filtered.append(dict(entry))

    return filtered[-max_entries:]


def query_blackboard(
    state: dict[str, Any],
    *,
    query: str,
    max_entries: int = 5,
) -> list[dict[str, Any]]:
    """Simple keyword search across blackboard entries.

    For more advanced semantic search, agents should use the
    ToolRegistry to call a dedicated search tool.
    """
    blackboard = state.get("agent_blackboard") or {}
    entries = blackboard.get("entries", [])
    if not query:
        return entries[-max_entries:]

    query_lower = query.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in entries:
        score = 0
        content = entry.get("content", "")
        if isinstance(content, dict):
            content_str = " ".join(
                str(v) for v in content.values() if isinstance(v, (str, int, float))
            )
        else:
            content_str = str(content)
        if query_lower in content_str.lower():
            score += 3
        if query_lower in str(entry.get("author", "")).lower():
            score += 2
        if query_lower in str(entry.get("type", "")).lower():
            score += 1
        if score > 0:
            scored.append((score, dict(entry)))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:max_entries]]


def entries_by_author(
    blackboard: dict[str, Any],
    author: str,
) -> list[dict[str, Any]]:
    return [
        dict(entry)
        for entry in blackboard.get("entries", [])
        if entry.get("author") == author
    ]
