"""Verifier: independent adversarial judgement (spec 05).

Runs on a different vendor from the actor. It receives the proposal, the simulation, the
policies in scope and the recent ledger, and returns approve, reject or escalate. It has no
route to modify the proposal: the return schema has no field for one.
"""

from __future__ import annotations

from core.action.models import ProposedAction, Verdict, VerdictReason
from core.models.router import Router, render
from core.models.types import Role
from twin.engine import SimulationReport


async def verify(
    router: Router,
    action: ProposedAction,
    report: SimulationReport,
    *,
    tier_name: str = "",
    trace_id: str = "",
) -> Verdict:
    context = {
        "operation": action.operation,
        "risk_class": action.risk_class,
        "cited_count": len(action.cited_context),
        "blast_radius": report.blast_radius.normalised,
        "violations": [v.model_dump() for v in report.violations],
        "tier_cap": tier_name,
    }
    messages = render(
        [
            ("system", "Assume the proposal is wrong. Find why. Cite a policy id or a graph fact."),
            ("user", f"{action.operation} with {action.arguments}. Simulation: {report.summary}"),
        ]
    )
    completion = await router.complete(
        Role.verifier, messages, tenant_id=action.tenant_id, context=context, trace_id=trace_id
    )
    data = completion.data
    return Verdict(
        action_id=action.id,
        decision=data.get("decision", "escalate"),
        reasons=[VerdictReason(**r) for r in data.get("reasons", [])],
        verifier_model=completion.model,
        trace_id=trace_id,
    )
