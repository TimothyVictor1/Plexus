from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from api.health import DependencyHealth, HttpCheck, TcpCheck, run_checks
from api.main import create_app


async def _ok() -> DependencyHealth:
    return DependencyHealth(name="ok-dep", status="ok", latency_ms=1.0)


async def _down() -> DependencyHealth:
    return DependencyHealth(name="down-dep", status="down", detail="ConnectionRefusedError")


async def _degraded() -> DependencyHealth:
    return DependencyHealth(name="slow-dep", status="degraded")


async def test_run_checks_aggregates_worst_status() -> None:
    assert (await run_checks([_ok, _ok])).status == "ok"
    assert (await run_checks([_ok, _degraded])).status == "degraded"
    assert (await run_checks([_ok, _degraded, _down])).status == "down"


async def test_tcp_check_reports_down_on_closed_port() -> None:
    result = await TcpCheck("closed", "127.0.0.1", 1, timeout_s=0.5)()
    assert result.status == "down"


async def test_http_check_reports_down_on_connect_error() -> None:
    result = await HttpCheck("nohttp", "http://127.0.0.1:1/health", timeout_s=0.5)()
    assert result.status == "down"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    app.state.health_checks = [_ok, _down]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_live(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_deep_health_returns_503_when_any_dependency_down(
    client: httpx.AsyncClient,
) -> None:
    r = await client.get("/v1/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "down"
    assert {d["name"] for d in body["dependencies"]} == {"ok-dep", "down-dep"}


async def test_openapi_is_versioned(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/openapi.json")
    assert r.status_code == 200
    assert "/v1/health" in r.json()["paths"]
