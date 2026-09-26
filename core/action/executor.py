"""The single write path to customer systems (spec 05, principle 1).

This is the only module in the repository permitted to call an adapter's write method or to
restore a PII token. Both rules are enforced by tests/architecture/test_import_boundaries.py,
and the database enforces the other half: executions.verdict_id is NOT NULL, so an execution
row cannot exist without a stored verdict.

Order of checks, all of which happen before a single token is restored:
  1. tenant and process pause flags (the kill switch)
  2. tier rules and the verdict
  3. adapter write capability and operation allow-list
  4. restore tokens, write, record
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from adapters._contract.base import WriteOp
from adapters.fixture.adapter import WriteDisabledError, get_adapter
from core.action.models import ExecutionRecord, HumanApproval, ProposedAction, Verdict
from core.db.pool import tenant_conn
from core.ledger import ledger
from core.ledger.models import Actor, NewLedgerEntry, Tier
from core.pii.boundary import TokenMap, UnknownTokenError, restore
from core.pii.vault import TokenVault
from twin.engine import SimulationReport

ALLOWED_OPERATIONS: dict[str, frozenset[str]] = {
    "clickup": frozenset({"clickup.create_task", "clickup.set_status", "clickup.delete"}),
    "accounting": frozenset({"accounting.approve_invoice"}),
    "gdrive": frozenset({"gdrive.share_file"}),
}


class OperationNotAllowedError(RuntimeError):
    """The operation is not on the adapter's allow-list."""


async def _paused(tenant_id: str, process_id: str) -> tuple[bool, str]:
    async with tenant_conn(tenant_id) as conn:
        tenant_paused = await conn.fetchval("SELECT paused FROM tenants WHERE id=$1", tenant_id)
        process_paused = await conn.fetchval(
            "SELECT paused FROM process_state WHERE tenant_id=$1 AND process_id=$2",
            tenant_id,
            process_id,
        )
    if tenant_paused:
        return True, "the tenant is paused"
    if process_paused:
        return True, "this process is paused"
    return False, ""


async def _token_map_for(tenant_id: str, arguments: dict[str, Any]) -> TokenMap:
    """Rebuild the token map for exactly the tokens this payload carries."""
    from core.pii.boundary import TOKEN_RE  # local import keeps the module surface small

    vault = TokenVault()
    tmap = TokenMap()
    blob = json.dumps(arguments, default=str)
    for match in TOKEN_RE.finditer(blob):
        token = match.group(0)
        if tmap.get(token) is not None:
            continue
        value = await vault.get(tenant_id, token)
        if value is None:
            raise UnknownTokenError(token)
        tmap.add(token, value, match.group(1))
    return tmap


async def execute(
    action: ProposedAction,
    verdict: Verdict,
    report: SimulationReport,
    tier: Tier,
    approval: HumanApproval | None = None,
) -> ExecutionRecord:
    tenant_id = action.tenant_id
    base_payload: dict[str, Any] = {
        "action_id": action.id,
        "operation": action.operation,
        "risk_class": action.risk_class,
        "blast_radius": report.blast_radius.normalised,
        "tier": tier.name,
        "verdict": verdict.decision,
    }

    async def record(entry_type: str, actor: Actor, extra: dict[str, Any]) -> None:
        await ledger.append(
            NewLedgerEntry(
                tenant_id=tenant_id,
                process_id=action.process_id,
                entry_type=entry_type,
                actor=actor,
                payload={**base_payload, **extra},
                trace_id=action.trace_id,
            )
        )

    system = Actor(kind="system", id="executor")

    # 1. kill switch --------------------------------------------------------------------
    paused, why = await _paused(tenant_id, action.process_id)
    if paused:
        await record("refusal", system, {"reason": why})
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="refused",
            entry_type="refusal",
            title="Refused, the kill switch is on",
            detail=f"Nothing was sent anywhere because {why}."
            " The refusal is itself a ledger entry.",
        )

    # 2. verdict and tier ---------------------------------------------------------------
    if verdict.decision == "reject":
        await record(
            "rejection",
            Actor(kind="model", id=str(verdict.verifier_model), role="verifier"),
            {"reasons": [r.model_dump() for r in verdict.reasons]},
        )
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="refused",
            entry_type="rejection",
            title="Refused, the verifier rejected the proposal",
            detail="A rejected proposal cannot execute at any tier, and no human override exists "
            "for a blocking policy. The rule has to be changed by an admin first.",
        )

    if verdict.decision == "escalate":
        await record("suggestion", system, {"escalated": True})
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="held",
            entry_type="suggestion",
            title="Sent to a person, the verifier escalated",
            detail="Escalation outranks the tier. Even at Autonomous this waits for an approver, "
            "with the proposal, the simulation and the reasons attached.",
        )

    if tier <= Tier.EXPLAIN:
        await record("shadow_run", system, {"would_have": action.operation})
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="held",
            entry_type="shadow_run",
            title="Nothing executed, this is a shadow run",
            detail=f"At {tier.name} the pipeline runs in full and files what it would have done. "
            "These runs are what the trust score is later computed from.",
        )

    if tier == Tier.SUGGEST:
        await record("suggestion", system, {})
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="held",
            entry_type="suggestion",
            title="Nothing executed, shown as a suggestion",
            detail="The proposal and the verdict land in a person's inbox. At this tier the "
            "executor never calls an adapter, whatever the verdict says.",
        )

    if tier == Tier.ACT_WITH_APPROVAL and (approval is None or approval.role != "approver"):
        await record("suggestion", system, {"awaiting": "approver"})
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="held",
            entry_type="suggestion",
            title="Waiting for an approver",
            detail="The verifier approved. At this tier a person holding the approver role has "
            "to confirm before anything is written.",
        )

    # 3. adapter capability and allow-list ----------------------------------------------
    adapter = get_adapter(action.target_source_id)
    allowed = ALLOWED_OPERATIONS.get(action.target_source_id, frozenset())
    if action.operation not in allowed:
        await record("refusal", system, {"reason": "operation not on the allow-list"})
        raise OperationNotAllowedError(action.operation)

    # 4. restore, write, record ----------------------------------------------------------
    try:
        token_map = await _token_map_for(tenant_id, action.arguments)
        clear_arguments = restore(action.arguments, token_map)
    except UnknownTokenError as exc:
        await record("refusal", system, {"reason": "unknown token", "token": str(exc)})
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="refused",
            entry_type="refusal",
            title="Refused, a token had no vault entry",
            detail="The write was abandoned rather than sending a placeholder to a real system.",
        )

    op = WriteOp(
        tenant_id=tenant_id,
        source_id=action.target_source_id,
        operation=action.operation,
        arguments=clear_arguments,
        idempotency_key=action.id,
    )
    try:
        result = await adapter.write(op)  # the one and only adapter write in the repo
    except WriteDisabledError:
        await record("refusal", system, {"reason": "adapter write capability disabled"})
        return ExecutionRecord(
            action_id=action.id,
            verdict_id=verdict.id,
            executed=False,
            outcome="refused",
            entry_type="refusal",
            title="Refused, this adapter cannot write",
            detail="Write capability is off for this adapter. Only an admin can enable it.",
        )

    # The restored payload is never logged or persisted; only the tokenised form is stored.
    execution_id = str(uuid.uuid4())
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO executions (id, tenant_id, action_id, verdict_id, approver,"
            " write_result, reversal) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            execution_id,
            tenant_id,
            action.id,
            verdict.id,
            json.dumps(approval.model_dump(), default=str) if approval else None,
            json.dumps(
                {
                    "ok": result.ok,
                    "message": result.message,
                    "ref": result.ref.model_dump() if result.ref else None,
                }
            ),
            json.dumps(result.reversal.model_dump(), default=str) if result.reversal else None,
        )
        await conn.execute(
            "UPDATE proposed_actions SET status='executed' WHERE tenant_id=$1 AND id=$2",
            tenant_id,
            action.id,
        )

    if approval is not None:
        await record("approval", Actor(kind="human", id=approval.subject, role=approval.role), {})
    await record("execution", system, {"execution_id": execution_id, "ref": result.message})

    detail = (
        f"Approved by {approval.subject} and written to {action.target_source_id}."
        if approval
        else f"Written to {action.target_source_id} automatically; a person was notified "
        "afterwards with a one-click reversal."
    )
    return ExecutionRecord(
        action_id=action.id,
        verdict_id=verdict.id,
        executed=True,
        outcome="executed",
        entry_type="execution",
        title="Executed after an approver confirmed" if approval else "Executed automatically",
        detail=detail,
        write_result={"ok": result.ok, "message": result.message},
        reversal=result.reversal.model_dump() if result.reversal else None,
    )


async def reverse(tenant_id: str, execution_id: str, approver: HumanApproval) -> ExecutionRecord:
    """Undo an execution through the same door, and record the reversal (which demotes)."""
    async with tenant_conn(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT e.*, a.process_id, a.target_source_id, a.trace_id FROM executions e"
            " JOIN proposed_actions a ON a.id = e.action_id"
            " WHERE e.tenant_id=$1 AND e.id=$2",
            tenant_id,
            execution_id,
        )
    if row is None:
        msg = f"no execution {execution_id}"
        raise LookupError(msg)
    if row["reversed_at"] is not None:
        return ExecutionRecord(
            action_id=str(row["action_id"]),
            executed=False,
            outcome="held",
            entry_type="reversal",
            title="Already reversed",
            detail="Nothing further to undo.",
        )

    raw = row["reversal"]
    reversal = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    adapter = get_adapter(row["target_source_id"])
    op = WriteOp(**reversal)
    result = await adapter.write(op)  # same single write path

    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "UPDATE executions SET reversed_at = now() WHERE tenant_id=$1 AND id=$2",
            tenant_id,
            execution_id,
        )
    await ledger.append(
        NewLedgerEntry(
            tenant_id=tenant_id,
            process_id=row["process_id"],
            entry_type="reversal",
            actor=Actor(kind="human", id=approver.subject, role=approver.role),
            payload={"execution_id": execution_id, "message": result.message},
            trace_id=row["trace_id"] or "",
        )
    )
    return ExecutionRecord(
        action_id=str(row["action_id"]),
        executed=True,
        outcome="executed",
        entry_type="reversal",
        title="Reversed",
        detail="The stored reversal ran through the executor. The process drops one tier "
        "automatically as a result.",
        write_result={"ok": result.ok, "message": result.message},
    )
