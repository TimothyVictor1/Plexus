"""Actor: proposes actions from a trigger plus graph context (spec 05).

The proposal is built from stored facts, and every claim in the rationale points at a cited
reference. The actor never executes and never sees a real value: everything here is tokenised.
"""

from __future__ import annotations

from typing import Any

from core.action.models import GraphRef, ProposedAction
from core.models.router import Router
from core.models.types import Role
from twin.engine import PredictedChange


async def plan(
    router: Router,
    *,
    tenant_id: str,
    process_id: str,
    trigger_event_id: str | None,
    template: dict[str, Any],
    cited: list[GraphRef],
    trace_id: str = "",
) -> ProposedAction:
    effects = [PredictedChange(**c) for c in template.get("expected_effects", [])]
    return ProposedAction(
        tenant_id=tenant_id,
        process_id=process_id,
        trigger_event_id=trigger_event_id,
        target_source_id=template["target_source_id"],
        operation=template["operation"],
        arguments=dict(template.get("arguments", {})),
        rationale=template["rationale"],
        cited_context=cited,
        expected_effects=effects,
        risk_class=template.get("risk_class", "low"),
        actor_model=router.model_id(Role.actor),
        trace_id=trace_id,
    )
