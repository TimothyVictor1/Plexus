"""Run the background worker.

    make worker

It connects to Temporal, registers the jobs, and creates the schedule if it is missing. Stop
it and the product keeps working; only the routine upkeep pauses.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleIntervalSpec,
    ScheduleSpec,
)
from temporalio.worker import Worker

from core.settings import get_settings
from workflows.jobs import (
    TASK_QUEUE,
    MaintenanceWorkflow,
    OneJobWorkflow,
    check_triggers_activity,
    list_tenants_activity,
    recompute_insights_activity,
    refresh_labels_activity,
    sync_connections_activity,
)

SCHEDULE_ID = "plexus-maintenance"
EVERY = timedelta(minutes=15)


async def ensure_schedule(client: Client) -> None:
    """Create the recurring run once. Restarting the worker must not duplicate it."""
    try:
        await client.create_schedule(
            SCHEDULE_ID,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    MaintenanceWorkflow.run,
                    id="plexus-maintenance-run",
                    task_queue=TASK_QUEUE,
                ),
                spec=ScheduleSpec(intervals=[ScheduleIntervalSpec(every=EVERY)]),
            ),
        )
        print(f"schedule created, every {EVERY}")
    except ScheduleAlreadyRunningError:
        print("schedule already exists", flush=True)


async def main() -> None:
    settings = get_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    await ensure_schedule(client)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[MaintenanceWorkflow, OneJobWorkflow],
        activities=[
            list_tenants_activity,
            sync_connections_activity,
            refresh_labels_activity,
            check_triggers_activity,
            recompute_insights_activity,
        ],
    )
    print(f"worker listening on {TASK_QUEUE}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
