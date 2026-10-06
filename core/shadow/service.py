"""The shadow workforce: agents that learn by watching, and earn the right to act.

An agent shadows the way a new colleague does. Work comes up, it writes down privately what it
would do, and it touches nothing. Later a person deals with that work, and the two are
compared. Do that a few hundred times and there is something almost no software has: a measured
track record gathered at zero risk, before anything was ever at stake.

That record is the argument. Nobody sensible answers "would you like AI to handle your
invoicing?" with yes. "On your last 112 invoices it would have agreed with you 105 times, here
are the 7 it got wrong, shall it draft the next one for your approval?" is a question a careful
person can actually answer.

Three rules hold the thing honest:

Predictions are written before the person acts, never after. A prediction made with the answer
in view is not evidence of anything.

A prediction is never rewritten or deleted — the database refuses both — for the same reason
the ledger is append-only.

Only settled predictions count. A pending one is not evidence in either direction, or an agent
could look flawless by predicting things nobody ever decides.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.db.pool import tenant_conn
from core.shadow.models import Scoreboard, Scorecard, ShadowRun

# How much of a track record is needed before an agent is considered for the next rung. Low
# enough to be reachable in a month of ordinary work, high enough that a lucky run of three
# proves nothing.
MIN_PREDICTIONS = 20
# What it has to be right about. An edit counts half: right idea, wrong words.
READY_AT = 0.85
EDIT_CREDIT = 0.5
# After this, an unanswered prediction stops waiting. Nobody is going to decide it now, and
# leaving it pending forever would quietly flatter the agent's record.
EXPIRE_AFTER_DAYS = 30
WINDOW_DAYS = 90


async def predict(
    tenant_id: str,
    *,
    process_id: str,
    agent: str,
    predicted: dict[str, Any],
    trigger_kind: str = "",
    dedupe_key: str = "",
    confidence: float = 0.0,
    review_item_id: str | None = None,
) -> str | None:
    """Record what an agent would do. Acts on nothing.

    Returns the run id, or None when this occurrence has already been predicted — one
    prediction per real-world event, however often the shadow pass runs.
    """
    run_id = str(uuid.uuid4())
    async with tenant_conn(tenant_id) as conn:
        row = await conn.fetchrow(
            "INSERT INTO shadow_runs"
            " (id, tenant_id, process_id, agent, trigger_kind, dedupe_key, review_item_id,"
            "  predicted, confidence)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)"
            " ON CONFLICT DO NOTHING RETURNING id",
            run_id,
            tenant_id,
            process_id,
            agent,
            trigger_kind,
            dedupe_key,
            review_item_id,
            json.dumps(predicted),
            confidence,
        )
    return str(row["id"]) if row else None


def _verdict_for(status: str, edited: bool) -> tuple[str, str]:
    """Translate what a person did into what it says about the prediction."""
    if status in {"approved", "executed"}:
        if edited:
            return "edited", "The person kept the idea and changed the wording."
        return "agreed", "The person approved it unchanged."
    if status in {"skipped", "rejected"}:
        return "rejected", "The person decided this should not happen at all."
    return "pending", ""


async def observe(
    tenant_id: str, review_item_id: str, *, status: str, edited: bool, observed: dict[str, Any]
) -> None:
    """Score the prediction that matches an item a person has just settled.

    Silent when there is no matching prediction: shadowing is something an agent does for the
    work it covers, and a person settling anything else is not evidence about it.
    """
    verdict, note = _verdict_for(status, edited)
    if verdict == "pending":
        return
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "UPDATE shadow_runs SET verdict=$3, observed=$4, observed_at=now(), note=$5"
            " WHERE tenant_id=$1 AND review_item_id=$2 AND verdict='pending'",
            tenant_id,
            review_item_id,
            verdict,
            json.dumps(observed),
            note,
        )


async def expire_stale(tenant_id: str, *, older_than_days: int = EXPIRE_AFTER_DAYS) -> int:
    """Stop waiting on predictions nobody is going to answer.

    Left pending forever they would quietly flatter every agent's record, because accuracy is
    computed over settled predictions only.
    """
    cutoff = datetime.now(tz=UTC) - timedelta(days=older_than_days)
    async with tenant_conn(tenant_id) as conn:
        result = await conn.execute(
            "UPDATE shadow_runs SET verdict='expired',"
            " note='Nobody decided this within the window.'"
            " WHERE tenant_id=$1 AND verdict='pending' AND predicted_at < $2",
            tenant_id,
            cutoff,
        )
    return int(result.split()[-1]) if result else 0


def _score(agreed: int, edited: int, rejected: int) -> tuple[float, float]:
    settled = agreed + edited + rejected
    if not settled:
        return 0.0, 0.0
    return agreed / settled, (agreed + edited * EDIT_CREDIT) / settled


def _verdict_text(card: Scorecard) -> str:
    if card.settled < MIN_PREDICTIONS:
        short = MIN_PREDICTIONS - card.settled
        return (
            f"Still watching. {card.settled} of {MIN_PREDICTIONS} decisions seen, "
            f"{short} to go before there is enough to judge by."
        )
    if card.weighted >= READY_AT:
        return (
            f"Right {card.accuracy * 100:.0f}% of the time, and close another "
            f"{card.edited} times. Ready to start suggesting, if you want it to."
        )
    return (
        f"Right {card.accuracy * 100:.0f}% of the time across {card.settled} decisions, "
        "which is not yet enough to act on. It keeps watching."
    )


async def scoreboard(tenant_id: str, *, window_days: int = WINDOW_DAYS) -> Scoreboard:
    """What every shadowing agent has earned so far."""
    since = datetime.now(tz=UTC) - timedelta(days=window_days)
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT process_id, agent,"
            " count(*) AS predictions,"
            " count(*) FILTER (WHERE verdict='agreed')   AS agreed,"
            " count(*) FILTER (WHERE verdict='edited')   AS edited,"
            " count(*) FILTER (WHERE verdict='rejected') AS rejected"
            " FROM shadow_runs WHERE tenant_id=$1 AND predicted_at >= $2"
            " GROUP BY process_id, agent ORDER BY predictions DESC",
            tenant_id,
            since,
        )
        names = {
            r["id"]: r["name"]
            for r in await conn.fetch(
                "SELECT id, name FROM processes WHERE tenant_id=$1", tenant_id
            )
        }

    cards: list[Scorecard] = []
    for row in rows:
        agreed, edited, rejected = row["agreed"], row["edited"], row["rejected"]
        accuracy, weighted = _score(agreed, edited, rejected)
        card = Scorecard(
            process_id=row["process_id"],
            process_name=names.get(row["process_id"], row["process_id"]),
            agent=row["agent"],
            predictions=row["predictions"],
            settled=agreed + edited + rejected,
            agreed=agreed,
            edited=edited,
            rejected=rejected,
            accuracy=round(accuracy, 3),
            weighted=round(weighted, 3),
            needs=max(MIN_PREDICTIONS - (agreed + edited + rejected), 0),
        )
        card.ready = card.settled >= MIN_PREDICTIONS and card.weighted >= READY_AT
        card.verdict_text = _verdict_text(card)
        cards.append(card)

    ready = [c for c in cards if c.ready]
    if not cards:
        summary = "No agent has watched anything yet. They start as soon as there is work to watch."
    elif ready:
        summary = (
            f"{len(ready)} of {len(cards)} agent{'' if len(cards) == 1 else 's'} "
            "earned enough of a record to start suggesting. Nothing moves until you say so."
        )
    else:
        one = len(cards) == 1
        summary = (
            f"{len(cards)} agent{'' if one else 's'} "
            f"{'is' if one else 'are'} watching, and "
            f"{'it has' if one else 'none has'} not earned enough to act yet. "
            "That is the point: it has to."
        )
    return Scoreboard(window_days=window_days, cards=cards, summary=summary)


async def runs_for(tenant_id: str, process_id: str, *, limit: int = 50) -> list[ShadowRun]:
    """The individual predictions behind a scorecard, so a number can be checked."""
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM shadow_runs WHERE tenant_id=$1 AND process_id=$2"
            " ORDER BY predicted_at DESC LIMIT $3",
            tenant_id,
            process_id,
            limit,
        )

    def _j(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    return [
        ShadowRun(
            id=str(r["id"]),
            tenant_id=r["tenant_id"],
            process_id=r["process_id"],
            agent=r["agent"],
            trigger_kind=r["trigger_kind"],
            dedupe_key=r["dedupe_key"],
            review_item_id=str(r["review_item_id"]) if r["review_item_id"] else None,
            predicted=_j(r["predicted"]) or {},
            predicted_at=r["predicted_at"],
            confidence=r["confidence"],
            verdict=r["verdict"],
            observed=_j(r["observed"]),
            observed_at=r["observed_at"],
            note=r["note"],
        )
        for r in rows
    ]
