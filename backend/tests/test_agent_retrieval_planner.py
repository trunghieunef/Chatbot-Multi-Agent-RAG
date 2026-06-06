from agent_service.contracts import AgentChatRequest
from agent_service.graph.retrieval_planner import (
    build_retrieval_plan,
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
