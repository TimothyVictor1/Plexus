"""Deterministic local provider (spec 09, `vendor: local`).

This is not a mock of an LLM: it is a rule-based reasoner that produces the same structured
output shape the hosted providers must produce, so the whole pipeline runs with no API key and
no data leaving the machine. That is the brief's principle 8 (local first) taken literally.

Swap to a hosted vendor by editing config/models.yaml; no caller changes.
"""

from __future__ import annotations

import time
from typing import Any

from core.models.types import Completion, Message, ModelId, Usage


class LocalProvider:
    vendor = "local"

    def __init__(self, model: str) -> None:
        self.model = model

    async def list_models(self) -> list[str]:
        return [self.model]

    async def complete(
        self,
        messages: list[Message],
        *,
        role: str,
        context: dict[str, Any] | None = None,
        schema: object | None = None,
        max_tokens: int = 4096,
    ) -> Completion:
        started = time.perf_counter()
        ctx = context or {}
        data = _reason(role, ctx)
        text = str(data.get("_text", ""))
        prompt_chars = sum(len(m.content) for m in messages)
        return Completion(
            text=text,
            data=data,
            model=ModelId(vendor=self.vendor, model=self.model),
            usage=Usage(
                input_tokens=prompt_chars // 4,
                output_tokens=max(1, len(text) // 4),
                cost_usd=0.0,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


def _reason(role: str, ctx: dict[str, Any]) -> dict[str, Any]:
    if role == "verifier":
        return _verify(ctx)
    if role == "workhorse":
        return {"_text": ctx.get("fallback_summary", "")}
    return {"_text": ""}


def _verify(ctx: dict[str, Any]) -> dict[str, Any]:
    """Adversarial review of a proposal against its simulation and policies.

    The stance the verifier prompt demands: assume the proposal is wrong and look for why.
    """
    violations = ctx.get("violations", [])
    risk = ctx.get("risk_class", "low")
    cited = int(ctx.get("cited_count", 0))
    blast = float(ctx.get("blast_radius", 0.0))
    tier_cap = ctx.get("tier_cap")

    reasons: list[dict[str, str]] = []
    decision = "approve"

    for v in violations:
        effect = v.get("effect")
        if effect == "block":
            decision = "reject"
            reasons.append(
                {
                    "kind": "policy",
                    "ref": v["rule_id"],
                    "text": f"{v['rule_id']} blocks this outright: {v['evidence']}.",
                }
            )
        elif effect in {"require_approver", "data_residency", "require_working_hours"}:
            if decision != "reject":
                decision = "escalate"
            reasons.append(
                {
                    "kind": "policy",
                    "ref": v["rule_id"],
                    "text": f"{v['rule_id']} requires a person: {v['evidence']}.",
                }
            )
        else:
            reasons.append(
                {
                    "kind": "policy",
                    "ref": v["rule_id"],
                    "text": f"{v['rule_id']} warns: {v['evidence']}.",
                }
            )

    if cited == 0:
        decision = "reject" if decision == "reject" else "escalate"
        reasons.append(
            {
                "kind": "uncertainty",
                "ref": "citations",
                "text": "The rationale cites no graph context, so none of its claims"
                " can be checked.",
            }
        )

    if risk == "high" and decision == "approve":
        decision = "escalate"
        reasons.append(
            {
                "kind": "simulation",
                "ref": "risk_class",
                "text": "The proposal declares itself high risk, which is capped below Autonomous.",
            }
        )

    if blast >= 0.6 and decision == "approve":
        decision = "escalate"
        reasons.append(
            {
                "kind": "simulation",
                "ref": "blast_radius",
                "text": f"Blast radius {blast:.2f} is wide enough to want a person on it.",
            }
        )

    if decision == "approve":
        reasons.append(
            {
                "kind": "policy",
                "ref": "none",
                "text": "No policy in scope is triggered.",
            }
        )
        reasons.append(
            {
                "kind": "graph_fact",
                "ref": "citations",
                "text": f"All {cited} cited references resolve to stored sources.",
            }
        )
        if tier_cap:
            reasons.append(
                {
                    "kind": "simulation",
                    "ref": "tier",
                    "text": f"Within what tier {tier_cap} permits.",
                }
            )

    return {"decision": decision, "reasons": reasons, "_text": decision}
