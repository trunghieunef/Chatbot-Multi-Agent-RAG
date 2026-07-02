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
                                   "sources": [{"rerank_score": 0.8}]}}
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
