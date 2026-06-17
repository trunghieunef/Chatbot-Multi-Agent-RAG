import pytest

from agent_service.contracts import AgentChatRequest, RetrievalTask
from agent_service.graph import retrieval_planner
from agent_service.graph.retrieval_planner import (
    build_retrieval_plan,
    execute_retrieval_plan,
    readiness_capabilities,
)


def _state(message, agents, readiness=None):
    return {
        "request": AgentChatRequest(
            request_id="req-plan",
            session_id="session-1",
            message=message,
        ),
        "agents_to_run": agents,
        "readiness": readiness or {
            "listings": {"status": "ready", "parent_count": 10, "chunk_count": 30},
            "legal": {"status": "ready", "parent_count": 2, "chunk_count": 9},
            "projects": {"status": "ready", "parent_count": 3, "chunk_count": 8},
            "news": {"status": "ready", "parent_count": 4, "chunk_count": 12},
        },
    }


def test_readiness_capabilities_distinguish_parent_and_semantic_index():
    caps = readiness_capabilities({
        "listings": {"status": "not_ready", "parent_count": 5, "chunk_count": 0},
    })

    assert caps["property"]["parent_ready"] is True
    assert caps["property"]["structured_search_ready"] is True
    assert caps["property"]["semantic_index_ready"] is False
    assert caps["property"]["market_aggregate_ready"] is True


def test_build_retrieval_plan_for_mixed_query_creates_property_and_legal_tasks():
    plan = build_retrieval_plan(_state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ, pháp lý ổn và có tiềm năng đầu tư không?",
        ["legal_advisor", "investment_advisor", "property_search"],
    ))

    tasks = {task.task_id: task for task in plan}
    assert "search_property_1" in tasks
    assert "search_legal_1" in tasks
    assert tasks["search_property_1"].tool == "search_listings"
    assert tasks["search_property_1"].filters["district"] == "Quan 7"
    assert tasks["search_property_1"].filters["max_price"] == 5.0
    assert tasks["search_property_1"].filters["property_type"] == "Can ho"
    assert tasks["search_property_1"].retrieved_for == ["property_search"]
    assert tasks["search_property_1"].dependency_mode == "none"
    assert tasks["search_legal_1"].filters == {"category": "legal"}


def test_investment_reuses_property_task_without_duplicate_listing_task():
    plan = build_retrieval_plan(_state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ để đầu tư",
        ["investment_advisor", "property_search"],
    ))

    listing_tasks = [task for task in plan if task.tool == "search_listings"]
    assert len(listing_tasks) == 1
    assert listing_tasks[0].retrieved_for == ["property_search"]


def test_planner_does_not_add_project_or_news_for_plain_investment_query():
    plan = build_retrieval_plan(_state(
        "Tìm căn hộ Quận 7 dưới 5 tỷ để đầu tư",
        ["investment_advisor", "property_search"],
    ))

    assert all(task.domain not in {"project", "news"} for task in plan)


def test_planner_adds_news_when_investment_query_mentions_market_movement():
    plan = build_retrieval_plan(_state(
        "Đầu tư căn hộ Quận 7, có tin tức biến động thị trường gần đây không?",
        ["investment_advisor", "news_agent", "property_search"],
    ))

    news_tasks = [task for task in plan if task.domain == "news"]
    assert len(news_tasks) == 1
    assert news_tasks[0].filters == {"exclude_category": "legal"}


def test_planner_adds_market_task_only_when_city_is_explicit():
    without_city = build_retrieval_plan(_state(
        "Dau tu can ho Quan 7",
        ["investment_advisor", "property_search"],
    ))
    with_city = build_retrieval_plan(_state(
        "Dau tu can ho Quan 7 tai Ho Chi Minh",
        ["investment_advisor", "property_search"],
    ))

    assert all(task.domain != "market" for task in without_city)
    market_tasks = [task for task in with_city if task.domain == "market"]
    assert len(market_tasks) == 1
    assert market_tasks[0].filters["city"] == "Ho Chi Minh"
    assert market_tasks[0].tool == "lookup_market_metrics"


@pytest.mark.asyncio
async def test_execute_plan_normalizes_listing_and_assigns_to_investment(monkeypatch):
    async def fake_run_tool(**kwargs):
        assert kwargs["parent_type"] == "listing"
        assert kwargs["top_k"] == 20
        assert kwargs["rerank_to"] == 5
        return [
            {
                "id": 100,
                "product_id": "p-100",
                "title": "Can ho Quan 7",
                "price": 4.8,
                "price_text": "4.8 ty",
                "area": 75,
                "area_text": "75 m2",
                "price_per_m2": 64,
                "district": "Quan 7",
                "city": "Ho Chi Minh",
                "legal_status": "So hong",
                "url": "https://example.test/p-100",
                "matched_chunk": {
                    "id": 501,
                    "chunk_type": "overview",
                    "text": "Can ho Quan 7 gia 4.8 ty",
                    "distance": 0.18,
                    "rerank_score": 0.91,
                },
            }
        ]

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_tool)
    state = _state(
        "Tim can ho Quan 7 duoi 5 ty de dau tu",
        ["property_search", "investment_advisor"],
    )
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query=state["request"].message,
            filters={"district": "Quan 7"},
            retrieved_for=["property_search"],
            top_k=20,
            rerank_top_k=5,
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    evidence_ids = update["evidence_for_agent"]["property_search"]
    assert evidence_ids == update["evidence_for_agent"]["investment_advisor"]
    evidence = update["evidence_by_id"][evidence_ids[0]]
    assert evidence.source_identity == "listing:p-100"
    assert evidence.facts["legal_status_claimed"] == "So hong"
    assert evidence.matched_chunks[0].vector_distance == 0.18
    assert evidence.matched_chunks[0].semantic_score is None
    assert evidence.matched_chunks[0].final_score == 0.91
    assert update["retrieval_results"]["search_property_1"].status == "completed"


@pytest.mark.asyncio
async def test_execute_plan_empty_result_has_empty_status(monkeypatch):
    async def fake_run_tool(**kwargs):
        return []

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_tool)
    state = _state("Tim can ho Quan 7", ["property_search"])
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query=state["request"].message,
            filters={},
            retrieved_for=["property_search"],
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    assert update["retrieval_results"]["search_property_1"].status == "empty"
    assert update["evidence_by_id"] == {}


@pytest.mark.asyncio
async def test_execute_plan_failure_is_isolated(monkeypatch):
    async def fake_run_tool(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_tool)
    state = _state("Phap ly mua can ho", ["legal_advisor"])
    plan = [
        RetrievalTask(
            task_id="search_legal_1",
            domain="legal",
            tool="search_articles",
            query=state["request"].message,
            filters={"category": "legal"},
            retrieved_for=["legal_advisor"],
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    result = update["retrieval_results"]["search_legal_1"]
    assert result.status == "failed"
    assert result.warnings[0].code == "retrieval_error"


@pytest.mark.asyncio
async def test_execute_plan_marks_hybrid_search_exception_as_failed(monkeypatch):
    async def exploding_hybrid_search(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "agent_service.tools.retrieval.hybrid_search",
        exploding_hybrid_search,
    )
    state = _state("Tim can ho Quan 7", ["property_search"])
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query=state["request"].message,
            filters={},
            retrieved_for=["property_search"],
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    result = update["retrieval_results"]["search_property_1"]
    assert result.status == "failed"
    assert result.error["message"] == "database unavailable"


@pytest.mark.asyncio
async def test_execute_plan_tolerates_non_numeric_chunk_scores(monkeypatch):
    async def fake_run_tool(**kwargs):
        return [
            {
                "id": 101,
                "product_id": "p-101",
                "title": "Can ho Quan 7",
                "matched_chunk": {
                    "id": 777,
                    "text": "Can ho Quan 7",
                    "distance": "bad",
                    "rerank_score": "n/a",
                },
            }
        ]

    monkeypatch.setattr(retrieval_planner, "_run_hybrid_tool", fake_run_tool)
    state = _state("Tim can ho Quan 7", ["property_search"])
    plan = [
        RetrievalTask(
            task_id="search_property_1",
            domain="property",
            tool="search_listings",
            query=state["request"].message,
            filters={},
            retrieved_for=["property_search"],
        )
    ]

    update = await execute_retrieval_plan(plan, state)

    evidence_id = update["retrieval_results"]["search_property_1"].evidence_ids[0]
    chunk = update["evidence_by_id"][evidence_id].matched_chunks[0]
    assert chunk.vector_distance is None
    assert chunk.rerank_score is None
    assert chunk.final_score is None


@pytest.mark.asyncio
async def test_market_task_skips_when_city_filter_missing():
    state = _state(
        "Tim can ho Quan 7 duoi 5 ty, co tiem nang dau tu khong?",
        ["investment_advisor", "property_search"],
    )
    task = RetrievalTask(
        task_id="market_lookup_1",
        domain="market",
        tool="lookup_market_metrics",
        query=state["request"].message,
        filters={"district": "Quan 7", "property_type": "Can ho"},
        retrieved_for=["investment_advisor"],
    )

    update = await execute_retrieval_plan([task], state)

    result = update["retrieval_results"]["market_lookup_1"]
    assert result.status == "skipped"
    assert result.skip_reason == "investment_market_data_missing"
    assert result.warnings[0].code == "investment_market_data_missing"


@pytest.mark.asyncio
async def test_market_task_normalizes_market_metric_evidence(monkeypatch):
    async def fake_lookup_market_metrics(filters):
        assert filters["city"] == "Ho Chi Minh"
        return [
            {
                "source_identity": "market:Quan 7:Can ho:avg_price_per_m2:current",
                "metric": "avg_price_per_m2",
                "value": 64,
                "unit": "million VND/m2",
                "location": {"city": "Ho Chi Minh", "district": "Quan 7"},
                "property_type": "Can ho",
                "period": "current_snapshot",
            }
        ]

    monkeypatch.setattr(
        "agent_service.tools.market.lookup_market_metrics",
        fake_lookup_market_metrics,
    )
    state = _state("Dau tu can ho Quan 7", ["investment_advisor"])
    task = RetrievalTask(
        task_id="market_lookup_1",
        domain="market",
        tool="lookup_market_metrics",
        query=state["request"].message,
        filters={
            "city": "Ho Chi Minh",
            "district": "Quan 7",
            "property_type": "Can ho",
        },
        retrieved_for=["investment_advisor"],
    )

    update = await execute_retrieval_plan([task], state)

    result = update["retrieval_results"]["market_lookup_1"]
    evidence_id = result.evidence_ids[0]
    evidence = update["evidence_by_id"][evidence_id]
    assert result.status == "completed"
    assert evidence.source_type == "market_metric"
    assert evidence.source_identity == "market:Quan 7:Can ho:avg_price_per_m2:current"
    assert evidence.facts["metric"] == "avg_price_per_m2"
    assert evidence.facts["value"] == 64
    assert update["evidence_for_agent"]["investment_advisor"] == [evidence_id]
