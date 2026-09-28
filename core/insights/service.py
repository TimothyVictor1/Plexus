"""Worth knowing (redesign B7).

Three things, ranked: where the most time goes, what changed since last month, and something
that is going well. Each is a fact computed from the event log, phrased by the language layer.
Nothing here is generated from scratch, so nothing here can be wrong about the numbers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from core.db.pool import tenant_conn
from core.processes import ProcessSummary, list_processes

Kind = Literal["bottleneck", "change", "smooth"]


class Insight(BaseModel):
    kind: Kind
    text: str
    sub: str
    health: str
    process_id: str


def _biggest_bottleneck(processes: list[ProcessSummary]) -> Insight | None:
    candidates = [p for p in processes if p.slowest.duration and p.slowest.text]
    if not candidates:
        return None
    worst = max(candidates, key=lambda p: p.slowest.duration.seconds)  # type: ignore[union-attr]
    assert worst.slowest.duration is not None
    return Insight(
        kind="bottleneck",
        text=f"{worst.slowest.text.capitalize()} takes {worst.slowest.duration.text}.",
        sub="The longest single wait across all your work.",
        health=worst.health,
        process_id=worst.id,
    )


async def _biggest_change(tenant_id: str, processes: list[ProcessSummary]) -> Insight | None:
    """How much happened this month against the month before."""
    now = datetime.now(tz=UTC)
    this_from, prev_from = now - timedelta(days=30), now - timedelta(days=60)

    best: tuple[float, ProcessSummary, int, int] | None = None
    for process in processes:
        object_filter = json.dumps([{"object_type": process.id}])
        async with tenant_conn(tenant_id) as conn:
            recent = await conn.fetchval(
                "SELECT count(*) FROM event_log WHERE tenant_id=$1 AND objects @> $2::jsonb"
                " AND ts >= $3",
                tenant_id,
                object_filter,
                this_from,
            )
            earlier = await conn.fetchval(
                "SELECT count(*) FROM event_log WHERE tenant_id=$1 AND objects @> $2::jsonb"
                " AND ts >= $3 AND ts < $4",
                tenant_id,
                object_filter,
                prev_from,
                this_from,
            )
        recent, earlier = int(recent or 0), int(earlier or 0)
        if earlier < 5 or recent == 0:
            continue  # too little to compare; saying anything would be noise
        change = (recent - earlier) / earlier
        if best is None or abs(change) > abs(best[0]):
            best = (change, process, recent, earlier)

    if best is None:
        return None
    change, process, recent, _earlier = best
    if abs(change) < 0.15:
        return None
    direction = "more" if change > 0 else "less"
    return Insight(
        kind="change",
        text=f"{process.name} happened {direction} this month than last.",
        sub=f"{recent} times in the last 30 days, {abs(round(change * 100))}% {direction}.",
        health=process.health,
        process_id=process.id,
    )


def _something_going_well(processes: list[ProcessSummary]) -> Insight | None:
    smooth = [p for p in processes if p.health == "smooth"]
    if not smooth:
        return None
    best = max(smooth, key=lambda p: p.case_count)
    return Insight(
        kind="smooth",
        text=f"{best.name} is running smoothly.",
        sub=f"{best.case_count} times, and it takes {best.total_duration.text}.",
        health="smooth",
        process_id=best.id,
    )


async def top_insights(tenant_id: str, limit: int = 3) -> list[Insight]:
    processes = await list_processes(tenant_id)
    if not processes:
        return []
    found = [
        _biggest_bottleneck(processes),
        await _biggest_change(tenant_id, processes),
        _something_going_well(processes),
    ]
    return [i for i in found if i is not None][:limit]
