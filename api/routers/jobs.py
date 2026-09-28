"""The work Plexus does on its own, and whether it is keeping up."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import needs, tenant_context
from core.db.pool import tenant_conn
from core.tenancy import Role, TenantContext

router = APIRouter(tags=["jobs"])

JOBS: dict[str, str] = {
    "sync_connections": "Check the connected tools for anything new",
    "refresh_labels": "Name each way of working in plain English",
    "check_triggers": "Look for work that has got stuck",
    "recompute_insights": "Work out what is worth knowing",
}


class JobRun(BaseModel):
    job: str
    description: str
    status: str
    detail: str
    started_at: datetime | None = None


class JobsView(BaseModel):
    jobs: list[JobRun]
    scheduled_every_minutes: int = 15


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
        jobs=[
            JobRun(
                job=name,
                description=description,
                status=str(latest.get(name, {}).get("status", "never run")),
                detail=str(latest.get(name, {}).get("detail", "")),
                started_at=latest.get(name, {}).get("started_at"),
            )
            for name, description in JOBS.items()
        ]
    )


@router.post("/jobs/{job}/run", response_model=JobRun)
async def run_job(job: str, ctx: TenantContext = Depends(needs(Role.admin))) -> JobRun:
    """Run one now rather than waiting for the schedule."""
    if job not in JOBS:
        raise HTTPException(404, "no such job")

    from temporalio.client import Client

    from core.settings import get_settings
    from workflows.jobs import TASK_QUEUE, OneJobWorkflow

    settings = get_settings()
    try:
        client = await Client.connect(
            settings.temporal_address, namespace=settings.temporal_namespace
        )
        result = await client.execute_workflow(
            OneJobWorkflow.run,
            args=[job, ctx.tenant_id],
            id=f"job-{job}-{ctx.tenant_id}-{datetime.now().timestamp():.0f}",
            task_queue=TASK_QUEUE,
        )
    except Exception as exc:
        raise HTTPException(
            503,
            "The background worker is not running. Start it with 'make worker'.",
        ) from exc

    detail = result.detail if hasattr(result, "detail") else json.dumps(result)
    return JobRun(
        job=job,
        description=JOBS[job],
        status="ok" if getattr(result, "ok", True) else "failed",
        detail=str(detail),
        started_at=datetime.now(),
    )
