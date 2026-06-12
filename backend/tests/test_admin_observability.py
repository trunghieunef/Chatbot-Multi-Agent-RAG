import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.models.agent_observability import (
    AgentRetrievalEvent,
    AgentTrace,
    AgentTraceStep,
    EvalRun,
)


def test_require_admin_user_allows_admin_user():
    from app.routers import admin

    user = SimpleNamespace(is_admin=True)

    assert admin.require_admin_user(user) is user


def test_require_admin_user_rejects_non_admin_user():
    from app.routers import admin

    with pytest.raises(HTTPException) as exc_info:
        admin.require_admin_user(SimpleNamespace(is_admin=False))

    assert exc_info.value.status_code == 403


def test_require_admin_user_treats_missing_flag_as_false():
    from app.routers import admin

    with pytest.raises(HTTPException) as exc_info:
        admin.require_admin_user(SimpleNamespace())

    assert exc_info.value.status_code == 403


def test_admin_router_is_included_in_main_app():
    from app.main import app

    paths = {route.path for route in app.routes}

    assert "/api/v1/admin/chat-traces" in paths
    assert "/api/v1/admin/agent-health" in paths


def test_admin_router_is_not_included_when_disabled(monkeypatch):
    import app.main as main_module
    from app.config import get_settings

    monkeypatch.setenv("CHATBOT_ADMIN_ENABLED", "false")
    get_settings.cache_clear()
    disabled_main = importlib.reload(main_module)

    paths = {route.path for route in disabled_main.app.routes}

    assert "/api/v1/admin/chat-traces" not in paths
    assert "/api/v1/admin/agent-health" not in paths

    monkeypatch.setenv("CHATBOT_ADMIN_ENABLED", "true")
    get_settings.cache_clear()
    importlib.reload(main_module)


def test_admin_routes_depend_on_require_admin_user():
    from app.routers import admin

    routes = [
        route
        for route in admin.router.routes
        if isinstance(route, APIRoute)
    ]

    assert routes
    for route in routes:
        assert any(
            dependency.call is admin.require_admin_user
            for dependency in route.dependant.dependencies
        ), route.path


def test_admin_migration_adds_user_is_admin_column():
    migration = importlib.import_module(
        "backend.alembic.versions.20260603_0011_add_user_is_admin"
    )
    migration_source = Path(migration.__file__).read_text(encoding="utf-8")

    assert migration.revision == "20260603_0011"
    assert migration.down_revision == "20260603_0010"
    assert "op.add_column" in migration_source
    assert '"users"' in migration_source
    assert '"is_admin"' in migration_source
    assert "sa.Boolean()" in migration_source
    assert "nullable=False" in migration_source
    assert "server_default=sa.false()" in migration_source
    assert 'op.drop_column("users", "is_admin")' in migration_source


def test_model_serializer_excludes_sqlalchemy_internal_state():
    from app.routers import admin

    trace = AgentTrace(
        request_id="req-admin-serializer",
        agents_used=["property_search"],
        trace_summary_json={"intent": "property_search"},
        full_trace_json={"nodes": []},
        readiness_json={"source": "ok"},
        latency_ms=12.5,
        status="success",
    )

    payload = admin.serialize_model_public_columns(trace)

    assert payload["request_id"] == "req-admin-serializer"
    assert payload["agents_used"] == ["property_search"]
    assert "_sa_instance_state" not in payload


def test_top_queries_returns_grouped_items():
    from app.routers import admin

    class FakeResult:
        def all(self):
            return [("Tim nha Quan 2", 3), ("Can ho Quan 7", 1)]

    class FakeDB:
        async def execute(self, query):
            self.query = query
            return FakeResult()

    response = asyncio.run(
        admin.top_queries(
            limit=20,
            user=SimpleNamespace(is_admin=True),
            db=FakeDB(),
        )
    )

    assert response == {
        "items": [
            {"query": "Tim nha Quan 2", "count": 3},
            {"query": "Can ho Quan 7", "count": 1},
        ]
    }


def test_chat_trace_search_route_precedes_request_id_route():
    from app.routers import admin

    paths = [
        route.path
        for route in admin.router.routes
        if isinstance(route, APIRoute)
    ]

    assert paths.index("/admin/chat-traces/search") < paths.index(
        "/admin/chat-traces/{request_id}"
    )


def test_search_chat_traces_returns_items_and_total():
    from app.routers import admin

    trace = AgentTrace(
        id=1,
        request_id="req-search",
        agents_used=["property_search"],
        trace_summary_json={"intent": "property_search"},
        full_trace_json={},
        readiness_json={},
        latency_ms=12.0,
        status="success",
    )

    class CountResult:
        def scalar(self):
            return 1

    class RowsResult:
        def scalars(self):
            return SimpleNamespace(all=lambda: [trace])

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, query):
            self.calls += 1
            return CountResult() if self.calls == 1 else RowsResult()

    response = asyncio.run(
        admin.search_chat_traces(
            q="req",
            status="success",
            intent="property_search",
            limit=50,
            offset=0,
            user=SimpleNamespace(is_admin=True),
            db=FakeDB(),
        )
    )

    assert response["total"] == 1
    assert response["items"] == [trace]


def test_chat_trace_detail_includes_normalized_children():
    from app.routers import admin

    trace = AgentTrace(
        id=1,
        request_id="req-detail",
        agents_used=["router"],
        trace_summary_json={},
        full_trace_json={"steps": []},
        readiness_json={},
        latency_ms=5.0,
        status="success",
    )
    step = AgentTraceStep(
        request_id="req-detail",
        step_name="router",
        status="success",
        latency_ms=1.0,
        input_json={},
        output_json={"intent": "property_search"},
    )
    retrieval = AgentRetrievalEvent(
        request_id="req-detail",
        tool_name="hybrid_search",
        filters_json={},
        result_count=2,
        latency_ms=2.0,
        status="success",
        metadata_json={},
    )
    eval_run = EvalRun(
        request_id="req-detail",
        graph_version="graph",
        prompt_version="prompt",
        model_name="model",
        status="completed",
    )

    class Result:
        def __init__(self, value):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def scalars(self):
            return SimpleNamespace(all=lambda: self.value)

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, query):
            self.calls += 1
            if self.calls == 1:
                return Result(trace)
            if self.calls == 2:
                return Result([step])
            if self.calls == 3:
                return Result([retrieval])
            return Result([eval_run])

    response = asyncio.run(
        admin.get_chat_trace(
            "req-detail",
            user=SimpleNamespace(is_admin=True),
            db=FakeDB(),
        )
    )

    assert response["request_id"] == "req-detail"
    assert response["steps"][0]["step_name"] == "router"
    assert response["retrieval_events"][0]["tool_name"] == "hybrid_search"
    assert response["eval_runs"][0]["status"] == "completed"


def test_agent_health_returns_grouped_trace_statuses():
    from app.routers import admin

    class FakeResult:
        def all(self):
            return [
                ("error", 1, 120.0),
                ("success", 2, 45.5),
            ]

    class FakeDB:
        async def execute(self, query):
            self.query = query
            return FakeResult()

    db = FakeDB()

    response = asyncio.run(
        admin.agent_health(user=SimpleNamespace(is_admin=True), db=db)
    )

    assert response == {
        "items": [
            {"status": "error", "count": 1, "avg_latency_ms": 120.0},
            {"status": "success", "count": 2, "avg_latency_ms": 45.5},
        ]
    }
