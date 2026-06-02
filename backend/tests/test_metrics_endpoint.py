import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_text(monkeypatch):
    async def no_db_refresh():
        return None

    monkeypatch.setattr("app.routers.metrics._refresh_gauges", no_db_refresh)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "realestate_chat_requests_total" in body
    assert "realestate_pipeline_runs_total" in body


@pytest.mark.asyncio
async def test_pipeline_health_returns_summary_per_dag():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/pipeline")

    assert response.status_code == 200
    body = response.json()
    assert "dags" in body
