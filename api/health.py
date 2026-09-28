"""Deep health checks per dependency (spec 11).

Phase 0 checks reachability (TCP connect, or HTTP GET for Presidio). Phase 1 upgrades each to a
client-level check (SELECT 1, Cypher RETURN 1, PING, Temporal namespace describe).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from core.settings import Settings

Status = Literal["ok", "degraded", "down"]


class DependencyHealth(BaseModel):
    name: str
    status: Status
    latency_ms: float | None = None
    detail: str | None = None


class HealthReport(BaseModel):
    status: Status
    dependencies: list[DependencyHealth]


Check = Callable[[], Awaitable[DependencyHealth]]


@dataclass(frozen=True)
class TcpCheck:
    name: str
    host: str
    port: int
    timeout_s: float = 2.0

    async def __call__(self) -> DependencyHealth:
        start = time.perf_counter()
        try:
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=self.timeout_s
            )
            writer.close()
            await writer.wait_closed()
        except (TimeoutError, OSError) as exc:
            return DependencyHealth(name=self.name, status="down", detail=type(exc).__name__)
        return DependencyHealth(
            name=self.name, status="ok", latency_ms=(time.perf_counter() - start) * 1000
        )


@dataclass(frozen=True)
class HttpCheck:
    name: str
    url: str
    timeout_s: float = 2.0

    async def __call__(self) -> DependencyHealth:
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.get(self.url)
        except httpx.HTTPError as exc:
            return DependencyHealth(name=self.name, status="down", detail=type(exc).__name__)
        latency = (time.perf_counter() - start) * 1000
        if response.status_code >= 500:
            return DependencyHealth(
                name=self.name, status="down", latency_ms=latency, detail=str(response.status_code)
            )
        if response.status_code >= 400:
            return DependencyHealth(
                name=self.name,
                status="degraded",
                latency_ms=latency,
                detail=str(response.status_code),
            )
        return DependencyHealth(name=self.name, status="ok", latency_ms=latency)


def _host_port(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url if "://" in url else f"tcp://{url}")
    return parsed.hostname or "localhost", parsed.port or default_port


def default_checks(settings: Settings) -> list[Check]:
    """The dependencies this deployment actually has.

    Not a fixed list, because the list differs per deployment. The full Compose stack has all
    of them; a serverless deployment has Postgres and nothing else. Reporting a service as
    down when this Plexus was never built to use it would make every such deployment look
    broken forever, so each check is included only when its address is configured — the same
    rule the model vendors already follow, where an empty credential means "not here".
    """
    from core.db.pool import dsn

    pg_host, pg_port = _host_port(dsn(settings), 5432)
    checks: list[Check] = [TcpCheck("postgres", pg_host, pg_port)]

    if settings.graph_enabled and settings.neo4j_uri:
        neo4j_host, neo4j_port = _host_port(settings.neo4j_uri, 7687)
        checks.append(TcpCheck("neo4j", neo4j_host, neo4j_port))

    if settings.redis_url:
        redis_host, redis_port = _host_port(settings.redis_url, 6379)
        checks.append(TcpCheck("redis", redis_host, redis_port))

    if settings.jobs_scheduler == "temporal" and settings.temporal_address:
        temporal_host, temporal_port = _host_port(settings.temporal_address, 7233)
        checks.append(TcpCheck("temporal", temporal_host, temporal_port))

    if settings.presidio_analyzer_url:
        checks.append(HttpCheck("presidio-analyzer", f"{settings.presidio_analyzer_url}/health"))
    if settings.presidio_anonymizer_url:
        checks.append(
            HttpCheck("presidio-anonymizer", f"{settings.presidio_anonymizer_url}/health")
        )
    return checks


async def run_checks(checks: list[Check]) -> HealthReport:
    results = list(await asyncio.gather(*(check() for check in checks)))
    statuses = {r.status for r in results}
    overall: Status = "ok"
    if "down" in statuses:
        overall = "down"
    elif "degraded" in statuses:
        overall = "degraded"
    return HealthReport(status=overall, dependencies=results)
