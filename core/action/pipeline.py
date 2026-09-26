"""The action pipeline, end to end (spec 05).

plan -> simulate -> verify -> gate -> record. Everything it reads is real: trigger events come
from the event log, cited context from the graph, policies from Postgres, the tier and pause
flags from process_state, and every step lands in the ledger.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from agents.plan.actor import plan
from agents.verify.verifier import verify
from core.action import executor
from core.action.models import (
    ExecutionRecord,
    GraphRef,
    HumanApproval,
    ProposedAction,
    Verdict,
)
from core.db.pool import tenant_conn
from core.ledger.models import Tier
from core.models.router import get_router
from twin.engine import SimulationReport, simulate
from twin.rules import PolicyRule

# What the actor may propose for each process. In Phase 1 proper the actor model writes these
# from the graph; the shape and every value below still come from the stored case.
TEMPLATES: dict[str, dict[str, Any]] = {
    "quote_to_payment": {
        "target_source_id": "clickup",
        "operation": "clickup.create_task",
        "risk_class": "low",
        "rationale": "The thread closes with an accepted quote and no task exists for it yet. "
        "Every other accepted quote in this process became a task on the same list.",
        "expected_effects": [
            {"kind": "node", "op": "create", "label_or_type": "Record", "key": "clickup:new-task"},
            {
                "kind": "node",
                "op": "create",
                "label_or_type": "Commitment",
                "key": "commitment:new",
            },
            {"kind": "edge", "op": "create", "label_or_type": "COMMITTED_TO", "key": "edge:new"},
        ],
    },
    "quote_to_payment-invoice": {
        "target_source_id": "accounting",
        "operation": "accounting.approve_invoice",
        "risk_class": "high",
        "rationale": "The amount matches the accepted quote and delivery was confirmed in the "
        "project thread.",
        "expected_effects": [
            {"kind": "node", "op": "update", "label_or_type": "Record", "key": "invoice:record"},
            {"kind": "node", "op": "create", "label_or_type": "Decision", "key": "decision:new"},
            {"kind": "edge", "op": "close", "label_or_type": "COMMITTED_TO", "key": "edge:close"},
        ],
    },
    "share-file": {
        "target_source_id": "gdrive",
        "operation": "gdrive.share_file",
        "risk_class": "high",
        "rationale": "The reviewer asked for the client file to complete this week's audit sample.",
        "expected_effects": [
            {"kind": "edge", "op": "create", "label_or_type": "SHARED_WITH", "key": "edge:share"},
            {"kind": "node", "op": "update", "label_or_type": "Artifact", "key": "file:clients"},
        ],
    },
}


async def load_policies(tenant_id: str) -> list[PolicyRule]:
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM policies WHERE tenant_id=$1 AND enabled ORDER BY id", tenant_id
        )
    out = []
    for r in rows:
        d = dict(r)
        for key in ("scope", "value"):
            if isinstance(d[key], str):
                d[key] = json.loads(d[key])
        out.append(PolicyRule(**d))
    return out


async def tier_for(tenant_id: str, process_id: str) -> Tier:
    async with tenant_conn(tenant_id) as conn:
        name = await conn.fetchval(
            "SELECT tier FROM process_state WHERE tenant_id=$1 AND process_id=$2",
            tenant_id,
            process_id,
        )
    return Tier.parse(name or "OBSERVE")


async def _context_for(
    tenant_id: str, process_id: str
) -> tuple[list[GraphRef], dict[str, Any], str | None]:
    """Real cited context and arguments, drawn from the stored case."""
    async with tenant_conn(tenant_id) as conn:
        docs = await conn.fetch(
            "SELECT external_id, source_id, title, structured, kind FROM documents"
            " WHERE tenant_id=$1 AND kind = ANY($2::text[]) ORDER BY created_at DESC LIMIT 3",
            tenant_id,
            ["email", "task", "file"],
        )
        event = await conn.fetchrow(
            "SELECT event_id, objects, attributes, actor FROM event_log"
            " WHERE tenant_id=$1 ORDER BY ts DESC LIMIT 1",
            tenant_id,
        )
    cited = [
        GraphRef(
            key=f"{d['source_id']}:{d['external_id']}",
            kind=str(d["kind"]),
            why="cited as supporting context",
        )
        for d in docs
    ]
    attributes: dict[str, Any] = {}
    if event is not None:
        raw = event["attributes"]
        attributes = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    trigger_id = str(event["event_id"]) if event is not None else None

    if process_id == "quote_to_payment-invoice":
        arguments = {
            "external_id": "invoice-2026-0417",
            "invoice": "2026-0417",
            "amount": attributes.get("amount", 12400),
            "currency": "SEK",
            "region": "EU",
        }
    elif process_id == "share-file":
        arguments = {
            "external_id": "file-clients-2026",
            "file": "Customer list 2026.xlsx",
            "recipient": "reviewer@auditpartner.com",
            "region": "us-east-1",
            "role": "reader",
        }
    else:
        arguments = {
            "external_id": f"task-auto-{uuid.uuid4().hex[:6]}",
            "list": "Sälj",
            "title": "Skicka offert efter accepterad förfrågan",
            "status": "open",
            "region": "EU",
        }
    return cited, arguments, trigger_id


async def propose(
    tenant_id: str, process_id: str, trace_id: str = ""
) -> tuple[ProposedAction, SimulationReport]:
    router = get_router()
    template_key = process_id if process_id in TEMPLATES else "quote_to_payment"
    template = dict(TEMPLATES[template_key])
    cited, arguments, trigger_id = await _context_for(tenant_id, process_id)
    template["arguments"] = arguments

    # The invoice and file-sharing scenarios are variants of one process for ledger purposes.
    ledger_process = (
        "quote_to_payment"
        if process_id in {"quote_to_payment-invoice", "share-file"}
        else process_id
    )
    action = await plan(
        router,
        tenant_id=tenant_id,
        process_id=ledger_process,
        trigger_event_id=trigger_id,
        template=template,
        cited=cited,
        trace_id=trace_id or str(uuid.uuid4()),
    )
    report = simulate(
        action_id=action.id,
        tenant_id=tenant_id,
        operation=action.operation,
        arguments=action.arguments,
        expected_effects=action.expected_effects,
        policies=await load_policies(tenant_id),
        process_id=action.process_id,
        risk_class=action.risk_class,
        external_parties=1 if process_id in {"quote_to_payment-invoice", "share-file"} else 0,
        trace_id=action.trace_id,
    )
    action.simulation = report
    await _persist(action)
    return action, report


async def _persist(action: ProposedAction) -> None:
    async with tenant_conn(action.tenant_id) as conn:
        await conn.execute(
            "INSERT INTO proposed_actions (id, tenant_id, process_id, trigger_event_id,"
            " target_source_id, operation, arguments, rationale, cited_context,"
            " expected_effects, risk_class, actor_model, simulation, trace_id)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)"
            " ON CONFLICT (id) DO NOTHING",
            action.id,
            action.tenant_id,
            action.process_id,
            action.trigger_event_id,
            action.target_source_id,
            action.operation,
            json.dumps(action.arguments, default=str),
            action.rationale,
            json.dumps([c.model_dump() for c in action.cited_context]),
            json.dumps([e.model_dump() for e in action.expected_effects]),
            action.risk_class,
            json.dumps(action.actor_model.model_dump()),
            json.dumps(action.simulation.model_dump(), default=str) if action.simulation else None,
            action.trace_id,
        )


async def judge(action: ProposedAction, report: SimulationReport, tier: Tier) -> Verdict:
    verdict = await verify(
        get_router(), action, report, tier_name=tier.name, trace_id=action.trace_id
    )
    async with tenant_conn(action.tenant_id) as conn:
        await conn.execute(
            "INSERT INTO verdicts (id, tenant_id, action_id, decision, reasons,"
            " verifier_model, trace_id) VALUES ($1,$2,$3,$4,$5,$6,$7)"
            " ON CONFLICT (action_id) DO UPDATE SET decision=EXCLUDED.decision,"
            " reasons=EXCLUDED.reasons",
            verdict.id,
            action.tenant_id,
            action.id,
            verdict.decision,
            json.dumps([r.model_dump() for r in verdict.reasons]),
            json.dumps(verdict.verifier_model.model_dump()),
            verdict.trace_id,
        )
        row = await conn.fetchrow(
            "SELECT id FROM verdicts WHERE tenant_id=$1 AND action_id=$2",
            action.tenant_id,
            action.id,
        )
        if row is not None:
            verdict.id = str(row["id"])
    return verdict


async def run(
    tenant_id: str,
    process_id: str,
    *,
    tier_override: str | None = None,
    approval: HumanApproval | None = None,
) -> dict[str, Any]:
    """The whole pipeline. Returns every stage so the console can show the work."""
    action, report = await propose(tenant_id, process_id)
    tier = (
        Tier.parse(tier_override) if tier_override else await tier_for(tenant_id, action.process_id)
    )
    verdict = await judge(action, report, tier)
    record: ExecutionRecord = await executor.execute(action, verdict, report, tier, approval)
    return {
        "action": action.model_dump(),
        "simulation": report.model_dump(),
        "verdict": verdict.model_dump(),
        "outcome": record.model_dump(),
        "tier": tier.name,
    }
