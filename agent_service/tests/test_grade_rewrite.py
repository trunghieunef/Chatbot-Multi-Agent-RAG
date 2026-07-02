from agent_service.graph.agentic_workflow import (
    _grade_decision, _relaxable_filters, _relax_filters,
)


def _state(results, filters, rnd=0):
    return {
        "_agent_results": results,
        "supervisor_plan": {"selected_agents": list(results.keys())},
        "routing_filters": filters,
        "correction_round": rnd,
    }


def test_zero_results_with_relaxable_filter_retries():
    results = {"property_search": {"status": "no_evidence", "sources": []}}
    state = _state(results, {"bedrooms": 5, "price_max": 2.0})
    assert _grade_decision(state) == "rewrite"


def test_zero_results_no_relaxable_filter_goes_synthesize():
    results = {"property_search": {"status": "no_evidence", "sources": []}}
    state = _state(results, {})  # nothing to relax → honest answer
    assert _grade_decision(state) == "synthesize"


def test_good_results_go_synthesize():
    results = {"property_search": {"status": "completed",
                                   "sources": [{"score": 0.8}]}}
    state = _state(results, {"bedrooms": 3})
    assert _grade_decision(state) == "synthesize"


def test_cap_stops_second_retry():
    results = {"property_search": {"status": "no_evidence", "sources": []}}
    state = _state(results, {"bedrooms": 5}, rnd=1)  # already retried once
    assert _grade_decision(state) == "synthesize"


def test_relax_drops_bedrooms_and_widens_price():
    relaxed = _relax_filters({"bedrooms": 5, "price_max": 2.0, "district": "Quận 1"})
    assert "bedrooms" not in relaxed
    assert relaxed["price_max"] == 2.4  # +20%
    assert "district" not in relaxed


def test_relaxable_true_false():
    assert _relaxable_filters({"bedrooms": 3}) is True
    assert _relaxable_filters({"listing_type": "sale"}) is False


def test_rerank_score_flows_from_matched_chunk_into_grade():
    """Regression: the score Cohere puts on matched_chunk must reach grade.

    Builds the AgentSource the way the specialist does (from a resolved
    listing dict carrying matched_chunk), dumps it, and feeds it to grade.
    If a specialist drops rerank_score, _best_rerank_score sees None and the
    weak-results retry branch silently dies — this test fails in that case.
    """
    from agent_service.contracts import AgentSource

    weak_listing = {
        "id": 1, "title": "Nhà xa trung tâm",
        "district": "Quận 7", "city": "TP.HCM",
        "matched_chunk": {"rerank_score": 0.05},  # weak match from Cohere
    }
    source = AgentSource(
        type="listing",
        id=weak_listing.get("id"),
        title=weak_listing.get("title"),
        score=(weak_listing.get("matched_chunk") or {}).get("rerank_score"),
    )
    results = {"property_search": {"status": "completed",
                                   "sources": [source.model_dump()]}}
    # Nonzero results but score below AGENT_GRADE_MIN_SCORE (0.2) + relaxable
    # filter → grade must choose to retry, not accept the weak answer.
    state = _state(results, {"bedrooms": 3})
    assert _grade_decision(state) == "rewrite"
