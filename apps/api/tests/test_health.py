"""Smoke tests for liveness/readiness/metrics."""
from __future__ import annotations

from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_ping_returns_ok(client: AsyncClient) -> None:
    r = await client.get("/api/v1/ping")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "api"


async def test_request_id_is_echoed(client: AsyncClient) -> None:
    r = await client.get("/health", headers={"X-Request-ID": "abc12345"})
    assert r.headers["x-request-id"] == "abc12345"


async def test_request_id_is_generated_when_missing(client: AsyncClient) -> None:
    r = await client.get("/health")
    rid = r.headers.get("x-request-id")
    assert rid and len(rid) >= 8


async def test_ready_reports_dependencies(client: AsyncClient) -> None:
    r = await client.get("/api/v1/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    assert "postgres" in body["checks"]
    assert "redis" in body["checks"]


async def test_metrics_exposes_prometheus_format(client: AsyncClient) -> None:
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    # generate_latest always emits at least the python_info metric
    assert "python_info" in r.text
