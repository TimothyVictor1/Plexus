"""The routine work Plexus does on its own, written once, free of any scheduler.

Temporal is how this work is *scheduled* and retried when Plexus runs on a host that can keep a
worker alive. That is the arrangement the engineering rules ask for and it stays the default.
But the job itself is just an async function against Postgres, and a serverless host has no
worker to run: there, the same function is called once per HTTP request by a cron trigger.

Both paths therefore import from here. There is one definition of each job, so what the console
reports having run is what actually ran, whichever scheduler started it.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

JOBS: dict[str, str] = {
    "sync_connections": "Check the connected tools for anything new",
    "refresh_labels": "Name each way of working in plain English",
    "check_triggers": "Look for work that has got stuck",
    "recompute_insights": "Work out what is worth knowing",
}


@dataclass
class JobInput:
    tenant_id: str


@dataclass
class JobResult:
    job: str
    tenant_id: str
    detail: str
    ok: bool = True


async def record(tenant_id: str, job: str, status: str, detail: str) -> None:
    """Every run lands in job_runs, so the background is as visible as anything clickable."""
    from core.db.pool import tenant_conn

    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO job_runs (id, tenant_id, job, status, detail, finished_at)"
            " VALUES ($1,$2,$3,$4,$5, now())",
            str(uuid.uuid4()),
            tenant_id,
            job,
            status,
            detail[:500],
        )


async def guarded(tenant_id: str, job: str, work: Callable[[str], Awaitable[str]]) -> JobResult:
    """Run one job and record the outcome either way. A failed job is news, not a crash."""
    try:
        detail = await work(tenant_id)
    except Exception as exc:
        await record(tenant_id, job, "failed", f"{type(exc).__name__}: {exc}")
        return JobResult(job=job, tenant_id=tenant_id, detail=str(exc), ok=False)
    await record(tenant_id, job, "ok", detail)
    return JobResult(job=job, tenant_id=tenant_id, detail=detail)


# ---------------------------------------------------------------- the jobs
async def refresh_labels(tenant_id: str) -> JobResult:
    async def work(t: str) -> str:
        from core.processes.service import refresh_labels as run

        results = await run(t)
        from_model = sum(1 for v in results.values() if v.startswith("model"))
        return f"named {len(results)} ways of working, {from_model} by the model"

    return await guarded(tenant_id, "refresh_labels", work)


async def check_triggers(tenant_id: str) -> JobResult:
    async def work(t: str) -> str:
        from core.review import create_from_triggers

        created = await create_from_triggers(t)
        return f"{len(created)} new things waiting for a person"

    return await guarded(tenant_id, "check_triggers", work)


async def recompute_insights(tenant_id: str) -> JobResult:
    async def work(t: str) -> str:
        from core.insights import top_insights

        found = await top_insights(t)
        return f"{len(found)} insights recomputed"

    return await guarded(tenant_id, "recompute_insights", work)


async def sync_connections(tenant_id: str) -> JobResult:
    async def work(t: str) -> str:
        from core.db.pool import tenant_conn

        # The demo connector has nothing new to pull. A real connector fetches here and
        # writes normalised events, and the miner picks them up on its next run.
        async with tenant_conn(t) as conn:
            rows = await conn.fetch(
                "SELECT category FROM connections WHERE tenant_id=$1 AND status='connected'", t
            )
            await conn.execute(
                "UPDATE connections SET last_sync = now()"
                " WHERE tenant_id=$1 AND status='connected'",
                t,
            )
        return f"checked {len(rows)} connected tools"

    return await guarded(tenant_id, "sync_connections", work)


BY_NAME: dict[str, Callable[[str], Awaitable[JobResult]]] = {
    "sync_connections": sync_connections,
    "refresh_labels": refresh_labels,
    "check_triggers": check_triggers,
    "recompute_insights": recompute_insights,
}

# The order a full maintenance pass runs in: pull first, then interpret what was pulled.
ORDER = ("sync_connections", "refresh_labels", "check_triggers", "recompute_insights")


async def run_one(tenant_id: str, job: str) -> JobResult:
    work = BY_NAME.get(job)
    if work is None:
        return JobResult(job=job, tenant_id=tenant_id, detail="no such job", ok=False)
    return await work(tenant_id)


async def all_tenants() -> list[str]:
    from core.db.pool import tenant_conn

    async with tenant_conn("bootstrap") as conn:
        rows = await conn.fetch("SELECT id FROM tenants ORDER BY id")
    return [r["id"] for r in rows]
