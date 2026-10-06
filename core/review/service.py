"""The review queue (redesign B5).

Plexus prepares something, a person says yes or no, and only then does anything happen.
Approving runs through the same executor as everything else, so the pause flag, the policies
and the verifier all still apply.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from agents.triggers.rules import Hit, check_all
from core.action import executor
from core.action.models import HumanApproval
from core.action.pipeline import judge, propose, tier_for
from core.db.pool import tenant_conn
from core.language.format import humanise
from core.ledger.models import Tier
from core.models.router import get_router, render
from core.models.types import ModelUnavailableError, Role, SchemaValidationError
from core.review.models import Decision, ReviewItem


class DraftBody(BaseModel):
    """Only the wording is the model's to write."""

    body: str


class Draft(BaseModel):
    """What Plexus proposes to send or do.

    The title and the reason come from the data: they are facts about what happened and how
    long it has been waiting, so a model must never be in a position to reword them. Only the
    message body is generated.
    """

    title: str
    why: str
    body: str


DRAFT_SYSTEM = """You write short, warm, professional messages for a small company.

Rules:
- Plain language. No jargon, no marketing tone, no exclamation marks.
- Keep placeholders exactly as given, in square brackets. Never invent a name, a number or a date.
- Three or four sentences at most.
- Write only the message itself. No subject line, no heading, no preamble.
- Never promise anything the company has not agreed to."""


def _fallback_draft(hit: Hit) -> Draft:
    """What a person reads when no model is reachable. Always correct, just plainer."""
    bodies = {
        "payment_reminder": (
            "Hello [customer], a quick reminder that invoice [number] is still open after "
            f"{hit.days_waiting} days. Let us know if anything is unclear and we will sort it "
            "out. Best regards, [your name]"
        ),
        "routine_order": (
            "Order: [what was asked for]. Supplier: [supplier]. This matches earlier orders "
            "that were approved without changes."
        ),
        "send_report": (
            "The monthly figures are ready and have been waiting "
            f"{hit.days_waiting} days. This sends them on for review."
        ),
    }
    return Draft(
        title=hit.trigger.title,
        why=hit.trigger.why.format(days=hit.days_waiting),
        body=bodies.get(hit.trigger.kind, "Plexus has prepared this for your approval."),
    )


def _headline(hit: Hit) -> tuple[str, str]:
    return hit.trigger.title, hit.trigger.why.format(days=hit.days_waiting)


async def _draft_for(tenant_id: str, hit: Hit) -> Draft:
    """Ask the model for the wording. The structure never depends on the answer."""
    fallback = _fallback_draft(hit)
    amount = hit.context.get("amount")
    facts = [
        f"Situation: {hit.trigger.kind.replace('_', ' ')}.",
        f"It has been waiting {humanise(hit.days_waiting * 86400)}.",
        "Use [customer], [number], [supplier], [your name] as placeholders where needed.",
    ]
    if amount:
        facts.append(f"An amount of {amount} is involved; refer to it as [amount].")
    title, why = _headline(hit)
    try:
        completion = await get_router().complete(
            Role.workhorse,
            render([("system", DRAFT_SYSTEM), ("user", "\n".join(facts))]),
            tenant_id=tenant_id,
            schema=DraftBody,
            max_tokens=1200,
        )
    except (ModelUnavailableError, SchemaValidationError):
        return fallback
    body = str(completion.data.get("body") or "").strip()
    if not body:
        return fallback
    return Draft(title=title, why=why, body=body)


async def _already_seen(tenant_id: str, hit: Hit) -> bool:
    async with tenant_conn(tenant_id) as conn:
        found = await conn.fetchval(
            "SELECT 1 FROM triggers_seen WHERE tenant_id=$1 AND process_id=$2 AND dedupe_key=$3",
            tenant_id,
            hit.trigger.process_id,
            hit.dedupe_key,
        )
    return found is not None


async def create_from_triggers(tenant_id: str, now: datetime | None = None) -> list[str]:
    """Turn stuck work into things waiting for a person. Background work, never a request."""
    created: list[str] = []
    for hit in await check_all(tenant_id, now):
        if await _already_seen(tenant_id, hit):
            continue

        action, report = await propose(tenant_id, hit.trigger.process_id)
        tier = await tier_for(tenant_id, hit.trigger.process_id)
        verdict = await judge(action, report, tier)
        draft = await _draft_for(tenant_id, hit)

        item_id = str(uuid.uuid4())
        async with tenant_conn(tenant_id) as conn:
            await conn.execute(
                "INSERT INTO review_items (id, tenant_id, process_id, action_id, kind, title,"
                " why, draft_text, draft_fields, approve_label)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                item_id,
                tenant_id,
                hit.trigger.process_id,
                action.id,
                hit.trigger.kind,
                draft.title,
                draft.why,
                draft.body,
                json.dumps(
                    {
                        "case": hit.case_id,
                        "days_waiting": hit.days_waiting,
                        "verdict": verdict.decision,
                        **hit.context,
                    }
                ),
                hit.trigger.approve_label,
            )
            await conn.execute(
                "INSERT INTO triggers_seen (tenant_id, process_id, dedupe_key)"
                " VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                tenant_id,
                hit.trigger.process_id,
                hit.dedupe_key,
            )
        # The shadow record of this: what the agent would do, written before anyone has
        # looked at it. Scored later against whatever the person actually decides.
        from core.shadow import service as shadow

        await shadow.predict(
            tenant_id,
            process_id=hit.trigger.process_id,
            agent=hit.trigger.kind,
            trigger_kind=hit.trigger.kind,
            dedupe_key=hit.dedupe_key,
            review_item_id=item_id,
            predicted={
                "operation": hit.trigger.operation,
                "title": draft.title,
                "draft": draft.body,
                "target": hit.trigger.target_source_id,
            },
            confidence=1.0 if verdict.decision == "approve" else 0.0,
        )
        created.append(item_id)
    return created


def _row_to_item(row: dict[str, Any], names: dict[str, str]) -> ReviewItem:
    fields = row["draft_fields"]
    return ReviewItem(
        id=str(row["id"]),
        process_id=row["process_id"],
        process_name=names.get(row["process_id"], row["process_id"]),
        action_id=str(row["action_id"]) if row["action_id"] else None,
        kind=row["kind"],
        title=row["title"],
        why=row["why"],
        draft_text=row["draft_text"],
        draft_fields=json.loads(fields) if isinstance(fields, str) else dict(fields or {}),
        approve_label=row["approve_label"],
        status=row["status"],
        result=row["result"] if isinstance(row["result"], dict) else None,
        error=row["error"],
        created_at=row["created_at"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
    )


async def _process_names(tenant_id: str) -> dict[str, str]:
    """The plain name each item belongs under, from the cache the language layer fills."""
    from core.processes import list_processes

    return {p.id: p.name for p in await list_processes(tenant_id)}


async def open_items(tenant_id: str) -> list[ReviewItem]:
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM review_items WHERE tenant_id=$1 AND status='open'"
            " ORDER BY created_at DESC LIMIT 50",
            tenant_id,
        )
    names = await _process_names(tenant_id)
    return [_row_to_item(dict(r), names) for r in rows]


async def done_today(tenant_id: str, now: datetime | None = None) -> list[ReviewItem]:
    since = (now or datetime.now(tz=UTC)) - timedelta(hours=24)
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM review_items WHERE tenant_id=$1 AND status <> 'open'"
            " AND decided_at >= $2 ORDER BY decided_at DESC LIMIT 50",
            tenant_id,
            since,
        )
    names = await _process_names(tenant_id)
    return [_row_to_item(dict(r), names) for r in rows]


async def count_open(tenant_id: str) -> int:
    async with tenant_conn(tenant_id) as conn:
        value = await conn.fetchval(
            "SELECT count(*) FROM review_items WHERE tenant_id=$1 AND status='open'", tenant_id
        )
    return int(value or 0)


async def _load(tenant_id: str, item_id: str) -> dict[str, Any] | None:
    async with tenant_conn(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM review_items WHERE tenant_id=$1 AND id=$2", tenant_id, item_id
        )
    return dict(row) if row else None


async def _settle(
    tenant_id: str,
    item_id: str,
    status: str,
    subject: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    draft_text: str | None = None,
) -> None:
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "UPDATE review_items SET status=$3, decided_by=$4, decided_at=now(),"
            " result=$5, error=$6, draft_text=coalesce($7, draft_text)"
            " WHERE tenant_id=$1 AND id=$2",
            tenant_id,
            item_id,
            status,
            subject,
            json.dumps(result) if result else None,
            error,
            draft_text,
        )

    from core.shadow import service as shadow

    await shadow.observe(
        tenant_id,
        item_id,
        status=status,
        edited=draft_text is not None,
        observed={"status": status, "by": subject, "edited_text": draft_text},
    )


async def skip(tenant_id: str, item_id: str, subject: str) -> Decision:
    """Skipping is a real answer: it counts against the process's record."""
    item = await _load(tenant_id, item_id)
    if item is None:
        msg = f"no review item {item_id}"
        raise LookupError(msg)
    if item["status"] != "open":
        return Decision(
            ok=False,
            status=item["status"],
            title="Already decided",
            detail="Someone has already dealt with this one.",
        )

    from core.ledger import ledger
    from core.ledger.models import Actor, NewLedgerEntry

    await ledger.append(
        NewLedgerEntry(
            tenant_id=tenant_id,
            process_id=item["process_id"],
            entry_type="rejection",
            actor=Actor(kind="human", id=subject, role="approver"),
            payload={"review_item": item_id, "reason": "skipped by a person"},
        )
    )
    await _settle(tenant_id, item_id, "skipped", subject)
    return Decision(
        ok=True,
        status="skipped",
        title="Skipped",
        detail="Nothing was sent. Plexus will remember that you passed on this one.",
    )


async def approve(
    tenant_id: str, item_id: str, subject: str, edited_text: str | None = None
) -> Decision:
    """Say yes. The write goes through the executor like every other write."""
    item = await _load(tenant_id, item_id)
    if item is None:
        msg = f"no review item {item_id}"
        raise LookupError(msg)
    if item["status"] != "open":
        return Decision(
            ok=False,
            status=item["status"],
            title="Already decided",
            detail="Someone has already dealt with this one.",
        )
    if not item["action_id"]:
        await _settle(tenant_id, item_id, "failed", subject, error="no action attached")
        return Decision(
            ok=False,
            status="failed",
            title="Could not run this",
            detail="Nothing was attached to carry out, so nothing was done.",
        )

    action, verdict, report = await _rebuild(tenant_id, str(item["action_id"]))
    tier = await tier_for(tenant_id, item["process_id"])
    if tier < Tier.ACT_WITH_APPROVAL:
        # A person saying yes is exactly what this rung means.
        tier = Tier.ACT_WITH_APPROVAL

    approval = HumanApproval(subject=subject, role="approver", at=datetime.now(tz=UTC))
    record = await executor.execute(action, verdict, report, tier, approval)

    status = "executed" if record.executed else "failed"
    await _settle(
        tenant_id,
        item_id,
        status,
        subject,
        result={
            "outcome": record.outcome,
            "title": record.title,
            "message": record.write_result.get("message", ""),
        },
        error=None if record.executed else record.detail,
        draft_text=edited_text,
    )
    return Decision(
        ok=record.executed,
        status=status,
        title=record.title,
        detail=record.detail,
        executed=record.executed,
    )


async def _rebuild(tenant_id: str, action_id: str) -> tuple[Any, Any, Any]:
    """Load the stored proposal, verdict and simulation back into objects."""
    from core.action.models import ProposedAction, Verdict, VerdictReason
    from core.models.types import ModelId
    from twin.engine import PredictedChange, SimulationReport

    async with tenant_conn(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT a.*, v.id AS verdict_id, v.decision, v.reasons, v.verifier_model"
            " FROM proposed_actions a LEFT JOIN verdicts v ON v.action_id = a.id"
            " WHERE a.tenant_id=$1 AND a.id=$2",
            tenant_id,
            action_id,
        )
    if row is None:
        msg = f"no action {action_id}"
        raise LookupError(msg)

    def j(value: Any) -> Any:
        return json.loads(value) if isinstance(value, str) else value

    action = ProposedAction(
        id=str(row["id"]),
        tenant_id=tenant_id,
        process_id=row["process_id"],
        trigger_event_id=str(row["trigger_event_id"]) if row["trigger_event_id"] else None,
        target_source_id=row["target_source_id"],
        operation=row["operation"],
        arguments=j(row["arguments"]),
        rationale=row["rationale"],
        expected_effects=[PredictedChange(**e) for e in j(row["expected_effects"])],
        risk_class=row["risk_class"],
        actor_model=ModelId(**j(row["actor_model"])),
        trace_id=row["trace_id"],
    )
    report = SimulationReport(**j(row["simulation"]))
    verdict = Verdict(
        id=str(row["verdict_id"]),
        action_id=action.id,
        decision=row["decision"],
        reasons=[VerdictReason(**r) for r in j(row["reasons"])],
        verifier_model=ModelId(**j(row["verifier_model"])),
        trace_id=action.trace_id,
    )
    return action, verdict, report
