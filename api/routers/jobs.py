"""The work Plexus does on its own, and whether it is keeping up."""

from __future__ import annotations

import hmac
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from api.deps import needs, tenant_context
from core.db.pool import tenant_conn
from core.settings import get_settings
from core.tenancy import Role, TenantContext
from workflows.tasks import JOBS, ORDER, all_tenants, run_one

router = APIRouter(tags=["jobs"])


class JobRun(BaseModel):
    job: str
    description: str
    status: str
    detail: str
    started_at: datetime | None = None
    ran_by: str = ""


class JobsView(BaseModel):
    jobs: list[JobRun]
    scheduled_every_minutes: int = 15
    scheduler: str = "temporal"


def _scheduler() -> str:
    """Which scheduler this deployment actually has.

    Temporal keeps a worker alive and owns retries, which is the arrangement the engineering
    rules ask for. A serverless host cannot keep a worker, so there the schedule is an HTTP
    cron that calls the same job functions. The console says which one is in use rather than
    implying a durable worker that is not there.
    """
    return "cron" if get_settings().jobs_scheduler == "cron" else "temporal"


@router.get("/jobs", response_model=JobsView)
async def jobs(ctx: TenantContext = Depends(tenant_context)) -> JobsView:
    """The latest run of each job, so the background is as visible as anything clickable."""
    async with tenant_conn(ctx.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ON (job) job, status, detail, started_at FROM job_runs"
            " WHERE tenant_id=$1 ORDER BY job, started_at DESC",
            ctx.tenant_id,
        )
    latest = {r["job"]: dict(r) for r in rows}
    return JobsView(
        scheduler=_scheduler(),
        jobs=[
            JobRun(
                job=name,
                description=description,
                status=str(latest.get(name, {}).get("status", "never run")),
                detail=str(latest.get(name, {}).get("detail", "")),
                started_at=latest.get(name, {}).get("started_at"),
            )
            for name, description in JOBS.items()
        ],
    )


async def _via_temporal(job: str, tenant_id: str) -> JobRun:
    from temporalio.client import Client

    from workflows.jobs import TASK_QUEUE, OneJobWorkflow

    settings = get_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    result = await client.execute_workflow(
        OneJobWorkflow.run,
        args=[job, tenant_id],
        id=f"job-{job}-{tenant_id}-{datetime.now().timestamp():.0f}",
        task_queue=TASK_QUEUE,
    )
    return JobRun(
        job=job,
        description=JOBS[job],
        status="ok" if getattr(result, "ok", True) else "failed",
        detail=str(getattr(result, "detail", result)),
        started_at=datetime.now(),
        ran_by="temporal",
    )


async def _inline(job: str, tenant_id: str) -> JobRun:
    """Run the job in this request. The same function the Temporal activity wraps.

    Only for a deployment with no worker to hand. It is one pass of one job, started by a
    person or a cron trigger and recorded in job_runs exactly as a worker run would be —
    not a loop, and not something a page waits on during normal use.
    """
    result = await run_one(tenant_id, job)
    return JobRun(
        job=job,
        description=JOBS[job],
        status="ok" if result.ok else "failed",
        detail=result.detail,
        started_at=datetime.now(),
        ran_by="cron",
    )


@router.post("/jobs/{job}/run", response_model=JobRun)
async def run_job(job: str, ctx: TenantContext = Depends(needs(Role.admin))) -> JobRun:
    """Run one now rather than waiting for the schedule."""
    if job not in JOBS:
        raise HTTPException(404, "no such job")

    if _scheduler() == "cron":
        return await _inline(job, ctx.tenant_id)

    try:
        return await _via_temporal(job, ctx.tenant_id)
    except Exception as exc:
        raise HTTPException(
            503,
            "The background worker is not running. Start it with 'make worker'.",
        ) from exc


class MaintenanceReport(BaseModel):
    organisations: int
    runs: list[JobRun]


@router.post("/jobs/maintenance", response_model=MaintenanceReport)
async def maintenance(
    authorization: str = Header(default=""),
    x_plexus_cron: str = Header(default=""),
) -> MaintenanceReport:
    """One full pass over every organisation, for a host that schedules over HTTP.

    The serverless equivalent of the Temporal schedule. It is not part of the console and
    carries no session, so it is gated on a shared secret rather than a role. With no secret
    configured it refuses outright, so an unconfigured deployment cannot be driven by a
    stranger who happens to know the path.

    A bearer token as well as our own header, because a hosted cron trigger chooses how it
    authenticates and we do not.
    """
    secret = get_settings().scheduler_secret
    if not secret:
        raise HTTPException(503, "No cron secret is configured, so this endpoint is closed.")
    bearer = authorization.removeprefix("Bearer ").strip()
    if not (hmac.compare_digest(bearer, secret) or hmac.compare_digest(x_plexus_cron, secret)):
        raise HTTPException(401, "Bad cron secret.")

    runs: list[JobRun] = []
    tenants = await all_tenants()
    for tenant_id in tenants:
        for name in ORDER:
            runs.append(await _inline(name, tenant_id))
    return MaintenanceReport(organisations=len(tenants), runs=runs)


@router.get("/jobs/maintenance", response_model=MaintenanceReport, include_in_schema=False)
async def maintenance_get(
    authorization: str = Header(default=""),
    x_plexus_cron: str = Header(default=""),
) -> MaintenanceReport:
    """The same pass, for a cron trigger that only sends GET. Not part of the documented API."""
    return await maintenance(authorization=authorization, x_plexus_cron=x_plexus_cron)
