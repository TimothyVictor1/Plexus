"""Temporal activities and workflows for the routine work (redesign B10).

Nothing here runs inside a request. Naming processes, looking for stuck work and recomputing
insights all talk to a model vendor or scan the whole event log, so a person waiting on a page
must never be waiting on them.

The jobs themselves live in `workflows/tasks.py`, free of any scheduler. This module is the
Temporal half: it wraps each one as an activity and gives them retries, timeouts and a schedule.
That is what the engineering rules ask for — anything long-running or waiting lives in a
workflow, never a bare loop — and it is the default whenever Plexus runs somewhere a worker can
stay alive.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from temporalio import activity, workflow

from workflows import tasks
from workflows.tasks import JOBS, JobInput, JobResult

TASK_QUEUE = "plexus-jobs"

__all__ = ["JOBS", "TASK_QUEUE", "JobInput", "JobResult", "MaintenanceWorkflow", "OneJobWorkflow"]


# ---------------------------------------------------------------- activities
@activity.defn
async def refresh_labels_activity(job: JobInput) -> JobResult:
    return await tasks.refresh_labels(job.tenant_id)


@activity.defn
async def check_triggers_activity(job: JobInput) -> JobResult:
    return await tasks.check_triggers(job.tenant_id)


@activity.defn
async def recompute_insights_activity(job: JobInput) -> JobResult:
    return await tasks.recompute_insights(job.tenant_id)


@activity.defn
async def sync_connections_activity(job: JobInput) -> JobResult:
    return await tasks.sync_connections(job.tenant_id)


@activity.defn
async def list_tenants_activity() -> list[str]:
    return await tasks.all_tenants()


ACTIVITIES = {
    "sync_connections": sync_connections_activity,
    "refresh_labels": refresh_labels_activity,
    "check_triggers": check_triggers_activity,
    "recompute_insights": recompute_insights_activity,
}


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
            for name in tasks.ORDER:
                results.append(
                    await workflow.execute_activity(
                        ACTIVITIES[name], job, start_to_close_timeout=RETRY
                    )
                )
        return results


@workflow.defn
class OneJobWorkflow:
    """A single job, on demand. What the console's Run now button starts."""

    @workflow.run
    async def run(self, job_name: str, tenant_id: str) -> JobResult:
        chosen = ACTIVITIES.get(job_name)
        if chosen is None:
            return JobResult(job=job_name, tenant_id=tenant_id, detail="no such job", ok=False)
        return await workflow.execute_activity(
            chosen, JobInput(tenant_id=tenant_id), start_to_close_timeout=RETRY
        )


def now() -> datetime:
    return datetime.now(tz=UTC)
