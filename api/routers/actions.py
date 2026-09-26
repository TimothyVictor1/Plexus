"""Inbox, the action pipeline, the ledger and the kill switch."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from adapters.fixture.adapter import get_adapter
from api.deps import needs, tenant_context
from core.action import executor
from core.action.models import HumanApproval
from core.action.pipeline import load_policies, run, tier_for
from core.db.pool import tenant_conn
from core.ledger import ledger
from core.ledger.models import Actor, NewLedgerEntry, Tier
from core.tenancy import Role, TenantContext

router = APIRouter(tags=["actions"])


def _j(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


class RunRequest(BaseModel):
    process_id: str = "quote_to_payment"
    tier: str | None = None
    approve: bool = False


@router.post("/actions/run")
async def run_pipeline(
    body: RunRequest, ctx: TenantContext = Depends(needs(Role.operator))
) -> dict[str, Any]:
    approval = None
    if body.approve:
        if not ctx.has(Role.approver):
            raise HTTPException(403, "approving requires the approver role")
        approval = HumanApproval(subject=ctx.subject, role="approver", at=datetime.now(tz=UTC))
    try:
        return await run(ctx.tenant_id, body.process_id, tier_override=body.tier, approval=approval)
    except KeyError as exc:
        raise HTTPException(400, f"unknown tier {exc}") from exc


@router.get("/inbox")
async def inbox(ctx: TenantContext = Depends(tenant_context)) -> dict[str, Any]:
    async with tenant_conn(ctx.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT a.*, v.decision, v.reasons, v.verifier_model, v.id AS verdict_id"
            " FROM proposed_actions a LEFT JOIN verdicts v ON v.action_id = a.id"
            " WHERE a.tenant_id=$1 AND a.status='pending'"
            " ORDER BY a.created_at DESC LIMIT 40",
            ctx.tenant_id,
        )
    items = []
    for r in rows:
        items.append(
            {
                "id": str(r["id"]),
                "process_id": r["process_id"],
                "operation": r["operation"],
                "arguments": _j(r["arguments"]),
                "rationale": r["rationale"],
                "risk_class": r["risk_class"],
                "cited_context": _j(r["cited_context"]),
                "simulation": _j(r["simulation"]),
                "actor_model": _j(r["actor_model"]),
                "created_at": r["created_at"],
                "verdict": None
                if r["decision"] is None
                else {
                    "id": str(r["verdict_id"]),
                    "decision": r["decision"],
                    "reasons": _j(r["reasons"]),
                    "verifier_model": _j(r["verifier_model"]),
                },
            }
        )
    return {"items": items}


@router.post("/inbox/{action_id}/decide")
async def decide(
    action_id: str,
    decision: str = Body(embed=True),
    ctx: TenantContext = Depends(needs(Role.approver)),
) -> dict[str, Any]:
    if decision not in {"approve", "reject"}:
        raise HTTPException(400, "decision must be approve or reject")

    async with tenant_conn(ctx.tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT a.*, v.id AS verdict_id, v.decision AS verdict_decision, v.reasons,"
            " v.verifier_model FROM proposed_actions a"
            " LEFT JOIN verdicts v ON v.action_id = a.id"
            " WHERE a.tenant_id=$1 AND a.id=$2",
            ctx.tenant_id,
            action_id,
        )
    if row is None:
        raise HTTPException(404, "no such action")
    if row["verdict_id"] is None:
        raise HTTPException(409, "no verdict stored for this action; nothing can execute")

    if decision == "reject":
        async with tenant_conn(ctx.tenant_id) as conn:
            await conn.execute(
                "UPDATE proposed_actions SET status='rejected' WHERE tenant_id=$1 AND id=$2",
                ctx.tenant_id,
                action_id,
            )
        await ledger.append(
            NewLedgerEntry(
                tenant_id=ctx.tenant_id,
                process_id=row["process_id"],
                entry_type="rejection",
                actor=Actor(kind="human", id=ctx.subject, role="approver"),
                payload={"action_id": action_id, "reason": "rejected by approver"},
                trace_id=row["trace_id"] or "",
            )
        )
        return {
            "outcome": "refused",
            "title": "Rejected by approver",
            "detail": "Nothing was written. The rejection is recorded against this process.",
        }

    # Approve: rebuild the stored objects and go through the executor. Nothing here writes.
    from core.action.models import ProposedAction, Verdict, VerdictReason  # local import
    from core.models.types import ModelId
    from twin.engine import PredictedChange, SimulationReport

    action = ProposedAction(
        id=str(row["id"]),
        tenant_id=ctx.tenant_id,
        process_id=row["process_id"],
        trigger_event_id=str(row["trigger_event_id"]) if row["trigger_event_id"] else None,
        target_source_id=row["target_source_id"],
        operation=row["operation"],
        arguments=_j(row["arguments"]),
        rationale=row["rationale"],
        expected_effects=[PredictedChange(**e) for e in _j(row["expected_effects"])],
        risk_class=row["risk_class"],
        actor_model=ModelId(**_j(row["actor_model"])),
        trace_id=row["trace_id"],
    )
    report = SimulationReport(**_j(row["simulation"]))
    verdict = Verdict(
        id=str(row["verdict_id"]),
        action_id=action.id,
        decision=row["verdict_decision"],
        reasons=[VerdictReason(**r) for r in _j(row["reasons"])],
        verifier_model=ModelId(**_j(row["verifier_model"])),
        trace_id=action.trace_id,
    )
    tier = await tier_for(ctx.tenant_id, action.process_id)
    if tier < Tier.ACT_WITH_APPROVAL:
        tier = Tier.ACT_WITH_APPROVAL  # a human approving is what this tier means
    approval = HumanApproval(subject=ctx.subject, role="approver", at=datetime.now(tz=UTC))
    record = await executor.execute(action, verdict, report, tier, approval)
    return record.model_dump()


@router.get("/executions")
async def executions(ctx: TenantContext = Depends(tenant_context)) -> dict[str, Any]:
    async with tenant_conn(ctx.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT e.id, e.action_id, e.approver, e.write_result, e.reversed_at,"
            " e.created_at, a.operation, a.process_id FROM executions e"
            " JOIN proposed_actions a ON a.id = e.action_id"
            " WHERE e.tenant_id=$1 ORDER BY e.created_at DESC LIMIT 40",
            ctx.tenant_id,
        )
    return {
        "executions": [
            {
                "id": str(r["id"]),
                "action_id": str(r["action_id"]),
                "operation": r["operation"],
                "process_id": r["process_id"],
                "approver": _j(r["approver"]),
                "write_result": _j(r["write_result"]),
                "reversed_at": r["reversed_at"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }


@router.post("/executions/{execution_id}/reverse")
async def reverse(
    execution_id: str, ctx: TenantContext = Depends(needs(Role.approver))
) -> dict[str, Any]:
    approver = HumanApproval(subject=ctx.subject, role="approver", at=datetime.now(tz=UTC))
    try:
        record = await executor.reverse(ctx.tenant_id, execution_id, approver)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return record.model_dump()


@router.get("/ledger")
async def ledger_entries(
    process_id: str | None = Query(default=None),
    entry_type: str | None = Query(default=None),
    limit: int = Query(default=80, le=500),
    ctx: TenantContext = Depends(tenant_context),
) -> dict[str, Any]:
    entries = await ledger.entries(ctx.tenant_id, process_id, entry_type, limit)
    chains = await ledger.verify_all(ctx.tenant_id)
    return {
        "entries": [e.model_dump() for e in entries],
        "chains": [c.model_dump() for c in chains],
        "chain_ok": all(c.ok for c in chains) if chains else True,
    }


@router.get("/policies")
async def policies(ctx: TenantContext = Depends(tenant_context)) -> dict[str, Any]:
    rules = await load_policies(ctx.tenant_id)
    return {"policies": [r.model_dump() for r in rules]}


@router.get("/adapters")
async def adapters(ctx: TenantContext = Depends(tenant_context)) -> dict[str, Any]:
    async with tenant_conn(ctx.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT source_id, count(*) AS docs FROM documents WHERE tenant_id=$1"
            " GROUP BY source_id ORDER BY source_id",
            ctx.tenant_id,
        )
    written = await get_adapter("clickup").records(ctx.tenant_id)
    return {
        "adapters": [
            {
                "id": r["source_id"],
                "documents": r["docs"],
                "write_enabled": r["source_id"] == "clickup",
            }
            for r in rows
        ],
        "records": written[:20],
    }


class PauseRequest(BaseModel):
    paused: bool
    process_id: str | None = None


@router.post("/pause")
async def pause(
    body: PauseRequest, ctx: TenantContext = Depends(needs(Role.approver))
) -> dict[str, Any]:
    actor = Actor(kind="human", id=ctx.subject, role="approver")
    async with tenant_conn(ctx.tenant_id) as conn:
        if body.process_id:
            await conn.execute(
                "UPDATE process_state SET paused=$3, updated_at=now()"
                " WHERE tenant_id=$1 AND process_id=$2",
                ctx.tenant_id,
                body.process_id,
                body.paused,
            )
        else:
            await conn.execute(
                "UPDATE tenants SET paused=$2 WHERE id=$1", ctx.tenant_id, body.paused
            )
    await ledger.append(
        NewLedgerEntry(
            tenant_id=ctx.tenant_id,
            process_id=body.process_id or "tenant",
            entry_type="pause" if body.paused else "unpause",
            actor=actor,
            payload={"scope": body.process_id or "tenant"},
            trace_id=ctx.trace_id,
        )
    )
    return {"paused": body.paused, "scope": body.process_id or "tenant"}


class PromoteRequest(BaseModel):
    process_id: str
    direction: str = "promote"


@router.post("/processes/promote")
async def promote(
    body: PromoteRequest, ctx: TenantContext = Depends(needs(Role.approver))
) -> dict[str, Any]:
    current = await tier_for(ctx.tenant_id, body.process_id)
    target = (
        Tier(min(Tier.AUTONOMOUS, current + 1))
        if body.direction == "promote"
        else Tier(max(Tier.OBSERVE, current - 1))
    )
    async with tenant_conn(ctx.tenant_id) as conn:
        await conn.execute(
            "UPDATE process_state SET tier=$3, updated_at=now()"
            " WHERE tenant_id=$1 AND process_id=$2",
            ctx.tenant_id,
            body.process_id,
            target.name,
        )
    await ledger.append(
        NewLedgerEntry(
            tenant_id=ctx.tenant_id,
            process_id=body.process_id,
            entry_type="promotion" if body.direction == "promote" else "demotion",
            actor=Actor(kind="human", id=ctx.subject, role="approver"),
            payload={"from": current.name, "to": target.name},
            trace_id=ctx.trace_id,
        )
    )
    return {"from": current.name, "to": target.name}


@router.post("/ledger/tamper")
async def tamper(ctx: TenantContext = Depends(needs(Role.admin))) -> dict[str, Any]:
    """Prove the chain detects tampering.

    The append-only trigger blocks UPDATE, so this disables it, edits one row, and restores it,
    which is exactly what an attacker with database access would have to do.
    """
    async with tenant_conn(ctx.tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT seq, process_id, payload FROM ledger_entries WHERE tenant_id=$1"
            " ORDER BY seq DESC LIMIT 1",
            ctx.tenant_id,
        )
        if row is None:
            raise HTTPException(404, "nothing in the ledger to tamper with")
        payload = _j(row["payload"])
        payload["tampered"] = True
        await conn.execute("ALTER TABLE ledger_entries DISABLE TRIGGER ledger_no_update")
        try:
            await conn.execute(
                "UPDATE ledger_entries SET payload=$3 WHERE tenant_id=$1 AND seq=$2",
                ctx.tenant_id,
                row["seq"],
                json.dumps(payload),
            )
        finally:
            await conn.execute("ALTER TABLE ledger_entries ENABLE TRIGGER ledger_no_update")
    status = await ledger.verify_chain(ctx.tenant_id, row["process_id"])
    return {"tampered_seq": row["seq"], "chain": status.model_dump()}
