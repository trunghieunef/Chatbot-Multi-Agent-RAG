from __future__ import annotations

from agent_service.contracts import Evidence, AgentSource
from agent_service.graph.blackboard import (
    BlackboardEntry,
    append_blackboard_entry,
    entries_by_author,
)


def _evidence(evidence_id: str = "ev_listing_1") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        retrieval_task_id="search_property_1",
        domain="property",
        source_type="listing",
        source_identity="listing:p1",
        record={"title": "Can ho Quan 7"},
        facts={"title": "Can ho Quan 7", "price": 4.8, "area": 75},
        source=AgentSource(
            type="listing",
            domain="property",
            id="listing:p1",
            title="Can ho Quan 7",
        ),
        retrieved_for=["investment_advisor"],
        assigned_to=["investment_advisor"],
    )


def test_append_blackboard_entry_keeps_only_known_evidence_ids():
    state = {
        "agent_blackboard": {"entries": []},
        "evidence_by_id": {"ev_listing_1": _evidence("ev_listing_1")},
    }

    updated = append_blackboard_entry(
        state,
        author="property_search",
        entry_type="property_summary",
        content={"summary": "Listing phu hop ngan sach"},
        evidence_ids=["ev_listing_1", "missing"],
        confidence="high",
        step_name="specialist_agents",
    )

    entries = updated["agent_blackboard"]["entries"]
    assert len(entries) == 1
    assert entries[0]["author"] == "property_search"
    assert entries[0]["evidence_ids"] == ["ev_listing_1"]
    assert entries[0]["confidence"] == "high"


def test_entries_by_author_filters_blackboard_entries():
    entry = BlackboardEntry(
        id="bb_property_search_1",
        author="property_search",
        type="property_summary",
        content={"summary": "ok"},
        evidence_ids=["ev1"],
        confidence="medium",
        created_at_step="specialist_agents",
    )
    blackboard = {"entries": [entry.model_dump(mode="python")]}

    assert entries_by_author(blackboard, "property_search")[0]["id"] == "bb_property_search_1"
    assert entries_by_author(blackboard, "legal_advisor") == []
