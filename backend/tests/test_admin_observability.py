import asyncio
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.models.agent_observability import AgentTrace


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


def test_top_queries_returns_placeholder_items():
    from app.routers import admin

    response = asyncio.run(admin.top_queries(user=SimpleNamespace(is_admin=True)))

    assert response == {"items": []}


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
