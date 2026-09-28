"""The work Plexus does on its own, in the background (redesign B10).

Nothing here runs inside a request. Naming processes, looking for stuck work and recomputing
insights all talk to a model vendor or scan the whole event log, so a person waiting on a page
must never be waiting on them.

Temporal runs them, which is what the engineering rules ask for: anything long-running or
waiting lives in a workflow, never a bare loop. Each run is recorded in job_runs so the
background is as visible as anything a person clicks.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from temporalio import activity, workflow

TASK_QUEUE = "plexus-jobs"


@dataclass
class JobInput:
    tenant_id: str


@dataclass
class JobResult:
    job: str
    tenant_id: str
    detail: str
    ok: bool = True


async def _record(tenant_id: str, job: str, status: str, detail: str) -> None:
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


async def _run(tenant_id: str, job: str, work: Callable[[str], Awaitable[str]]) -> JobResult:
    try:
        detail = await work(tenant_id)
    except Exception as exc:
        await _record(tenant_id, job, "failed", f"{type(exc).__name__}: {exc}")
        return JobResult(job=job, tenant_id=tenant_id, detail=str(exc), ok=False)
    await _record(tenant_id, job, "ok", detail)
    return JobResult(job=job, tenant_id=tenant_id, detail=detail)


# ---------------------------------------------------------------- activities
@activity.defn
async def refresh_labels_activity(job: JobInput) -> JobResult:
    async def work(tenant_id: str) -> str:
        from core.processes.service import refresh_labels

        results = await refresh_labels(tenant_id)
        from_model = sum(1 for v in results.values() if v.startswith("model"))
        return f"named {len(results)} ways of working, {from_model} by the model"

    return await _run(job.tenant_id, "refresh_labels", work)


@activity.defn
async def check_triggers_activity(job: JobInput) -> JobResult:
    async def work(tenant_id: str) -> str:
        from core.review import create_from_triggers

        created = await create_from_triggers(tenant_id)
        return f"{len(created)} new things waiting for a person"

    return await _run(job.tenant_id, "check_triggers", work)


@activity.defn
async def recompute_insights_activity(job: JobInput) -> JobResult:
    async def work(tenant_id: str) -> str:
        from core.insights import top_insights

        found = await top_insights(tenant_id)
        return f"{len(found)} insights recomputed"

    return await _run(job.tenant_id, "recompute_insights", work)


@activity.defn
async def sync_connections_activity(job: JobInput) -> JobResult:
    async def work(tenant_id: str) -> str:
        from core.db.pool import tenant_conn

        # The demo connector has nothing new to pull. A real connector fetches here and
        # writes normalised events, and the miner picks them up on its next run.
        async with tenant_conn(tenant_id) as conn:
            rows = await conn.fetch(
                "SELECT category FROM connections WHERE tenant_id=$1 AND status='connected'",
                tenant_id,
            )
            await conn.execute(
                "UPDATE connections SET last_sync = now()"
                " WHERE tenant_id=$1 AND status='connected'",
                tenant_id,
            )
        return f"checked {len(rows)} connected tools"

    return await _run(job.tenant_id, "sync_connections", work)


@activity.defn
async def list_tenants_activity() -> list[str]:
    from core.db.pool import tenant_conn

    async with tenant_conn("bootstrap") as conn:
        rows = await conn.fetch("SELECT id FROM tenants ORDER BY id")
    return [r["id"] for r in rows]


# ---------------------------------------------------------------- workflows
RETRY = timedelta(minutes=10)


@workflow.defn
class MaintenanceWorkflow:
    """One pass of the routine work, for every organisation."""

    @workflow.run
    async def run(self) -> list[JobResult]:
        tenants = await workflow.execute_activity(
            list_tenants_activity, start_to_close_timeout=timedelta(seconds=30)
        )
        results: list[JobResult] = []
        for tenant_id in tenants:
            job = JobInput(tenant_id=tenant_id)
            for step in (
                sync_connections_activity,
                refresh_labels_activity,
                check_triggers_activity,
                recompute_insights_activity,
            ):
                results.append(
                    await workflow.execute_activity(step, job, start_to_close_timeout=RETRY)
                )
        return results


@workflow.defn
class OneJobWorkflow:
    """A single job, on demand. What the console's Run now button starts."""

    @workflow.run
    async def run(self, job_name: str, tenant_id: str) -> JobResult:
        activities = {
            "sync_connections": sync_connections_activity,
            "refresh_labels": refresh_labels_activity,
            "check_triggers": check_triggers_activity,
            "recompute_insights": recompute_insights_activity,
        }
        chosen = activities.get(job_name)
        if chosen is None:
            return JobResult(job=job_name, tenant_id=tenant_id, detail="no such job", ok=False)
        return await workflow.execute_activity(
            chosen, JobInput(tenant_id=tenant_id), start_to_close_timeout=RETRY
        )


def now() -> datetime:
    return datetime.now(tz=UTC)
