"""Spotting the moment a process needs a person (redesign B5).

Detection is deterministic: it reads the event log and finds cases that have reached a point
and stopped. Only the wording of the draft comes from a model, and there is a template
fallback for when no model is reachable.

A process must be at Suggests or higher before anything is created, and each real-world
occurrence produces exactly one item however often the check runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from core.db.pool import tenant_conn
from core.ledger.models import Tier


@dataclass(frozen=True)
class Trigger:
    """One thing worth telling a person about."""

    key: str
    process_id: str
    kind: str
    # The step a case must have reached, and the step it must NOT have reached.
    reached: str
    not_reached: str
    # How long it must have been sitting there.
    waiting_days: float
    title: str
    why: str
    approve_label: str
    operation: str
    target_source_id: str


TRIGGERS: tuple[Trigger, ...] = (
    Trigger(
        key="invoice_overdue",
        process_id="quote_to_payment",
        kind="payment_reminder",
        reached="invoiced",
        not_reached="paid",
        waiting_days=14,
        title="Send a payment reminder",
        why="An invoice has been open for {days} days. Plexus has written a friendly reminder.",
        approve_label="Approve and send",
        operation="clickup.create_task",
        target_source_id="clickup",
    ),
    Trigger(
        key="order_pending",
        process_id="purchasing",
        kind="routine_order",
        reached="requested",
        not_reached="approved",
        waiting_days=2,
        title="Approve a routine order",
        why="A request has been waiting {days} days. Similar ones have been approved before.",
        approve_label="Approve order",
        operation="clickup.create_task",
        target_source_id="clickup",
    ),
    Trigger(
        key="report_ready",
        process_id="monthly_reporting",
        kind="send_report",
        reached="created",
        not_reached="sent",
        waiting_days=1,
        title="Send the monthly report",
        why="The numbers have been ready for {days} days and nobody has sent them on.",
        approve_label="Approve and send",
        operation="clickup.create_task",
        target_source_id="clickup",
    ),
)


@dataclass
class Hit:
    trigger: Trigger
    case_id: str
    days_waiting: int
    reached_at: datetime
    context: dict[str, Any]

    @property
    def dedupe_key(self) -> str:
        return f"{self.trigger.key}:{self.case_id}"


async def _tier_of(tenant_id: str, process_id: str) -> Tier:
    async with tenant_conn(tenant_id) as conn:
        name = await conn.fetchval(
            "SELECT tier FROM process_state WHERE tenant_id=$1 AND process_id=$2",
            tenant_id,
            process_id,
        )
    return Tier.parse(name or "OBSERVE")


async def find(tenant_id: str, trigger: Trigger, now: datetime | None = None) -> list[Hit]:
    """Cases that reached one step, never reached the next, and have sat there long enough."""
    now = now or datetime.now(tz=UTC)
    cutoff = now - timedelta(days=trigger.waiting_days)
    object_filter = json.dumps([{"object_type": trigger.process_id}])

    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            """
            WITH cases AS (
              SELECT obj->>'object_id' AS case_id, verb, ts, attributes
              FROM event_log,
                   LATERAL jsonb_array_elements(objects) AS obj
              WHERE tenant_id = $1
                AND objects @> $2::jsonb
                AND obj->>'object_type' = $3
            ),
            reached AS (
              SELECT case_id, min(ts) AS at, (array_agg(attributes ORDER BY ts))[1] AS attrs
              FROM cases WHERE verb = $4 GROUP BY case_id
            ),
            finished AS (
              SELECT DISTINCT case_id FROM cases WHERE verb = $5
            )
            SELECT r.case_id, r.at, r.attrs
            FROM reached r
            LEFT JOIN finished f ON f.case_id = r.case_id
            WHERE f.case_id IS NULL AND r.at <= $6
            ORDER BY r.at
            """,
            tenant_id,
            object_filter,
            trigger.process_id,
            trigger.reached,
            trigger.not_reached,
            cutoff,
        )

    hits: list[Hit] = []
    for row in rows:
        attrs = row["attrs"]
        context = json.loads(attrs) if isinstance(attrs, str) else dict(attrs or {})
        hits.append(
            Hit(
                trigger=trigger,
                case_id=row["case_id"],
                days_waiting=max(0, (now - row["at"]).days),
                reached_at=row["at"],
                context=context,
            )
        )
    return hits


async def check_all(tenant_id: str, now: datetime | None = None) -> list[Hit]:
    """Every trigger whose process has earned the right to suggest things."""
    hits: list[Hit] = []
    for trigger in TRIGGERS:
        if await _tier_of(tenant_id, trigger.process_id) < Tier.SUGGEST:
            continue
        hits.extend(await find(tenant_id, trigger, now))
    return hits
