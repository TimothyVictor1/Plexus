"""Digital twin: simulate an action against a copy of the graph (spec 03).

The engine never touches the live store, and the plain-language summary is generated from the
structured diff only, then post-checked so the model cannot invent an effect.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from twin.rules import PolicyRule, PolicyViolation, evaluate


class PredictedChange(BaseModel):
    kind: Literal["node", "edge"]
    op: Literal["create", "update", "close"]
    label_or_type: str
    key: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class BlastRadius(BaseModel):
    records_touched: int = 0
    money_touched: float = 0.0
    external_parties: int = 0
    normalised: float = 0.0


class SimulationReport(BaseModel):
    action_id: str
    tenant_id: str
    changes: list[PredictedChange] = Field(default_factory=list)
    violations: list[PolicyViolation] = Field(default_factory=list)
    affected_commitments: list[str] = Field(default_factory=list)
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    summary: str = ""
    trace_id: str = ""

    @property
    def blocked(self) -> bool:
        return any(v.effect == "block" for v in self.violations)

    @property
    def needs_approver(self) -> bool:
        return any(v.effect in {"require_approver", "data_residency"} for v in self.violations)


def compute_blast_radius(
    changes: list[PredictedChange], arguments: dict[str, Any], external_parties: int
) -> BlastRadius:
    money = 0.0
    for key in ("amount", "total", "sum", "belopp"):
        raw = arguments.get(key)
        if isinstance(raw, (int, float)):
            money = float(raw)
            break
    records = len(changes)
    # Normalised 0..1: records saturate at 20, money at 100 000 SEK, parties at 5.
    normalised = min(
        1.0,
        0.4 * min(records / 20.0, 1.0)
        + 0.4 * min(money / 100_000.0, 1.0)
        + 0.2 * min(external_parties / 5.0, 1.0),
    )
    return BlastRadius(
        records_touched=records,
        money_touched=money,
        external_parties=external_parties,
        normalised=round(normalised, 3),
    )


def describe(changes: list[PredictedChange], violations: list[PolicyViolation]) -> str:
    """Deterministic summary built from the diff alone. The workhorse model may rewrite this,
    but `summary_mentions_only_diff` gates whatever it returns."""
    if not changes:
        body = "Nothing in the graph would change."
    else:
        creates = sum(1 for c in changes if c.op == "create")
        updates = sum(1 for c in changes if c.op == "update")
        closes = sum(1 for c in changes if c.op == "close")
        parts = []
        if creates:
            parts.append(f"{creates} new {'node' if creates == 1 else 'nodes'} or edges")
        if updates:
            parts.append(f"{updates} updated")
        if closes:
            parts.append(f"{closes} closed")
        body = "Would write " + ", ".join(parts) + "."
    if violations:
        names = ", ".join(sorted({v.rule_id for v in violations}))
        body += f" Policy in scope is triggered: {names}."
    else:
        body += " No policy in scope is triggered."
    return body


def summary_mentions_only_diff(summary: str, changes: list[PredictedChange]) -> bool:
    """Reject a summary naming an entity absent from the diff (spec 03 failure mode)."""
    known = {c.key.lower() for c in changes} | {c.label_or_type.lower() for c in changes}
    for token in set(filter(None, (w.strip(".,;:()").lower() for w in summary.split()))):
        if token.startswith(("record:", "node:", "edge:")) and token not in known:
            return False
    return True


def simulate(
    *,
    action_id: str,
    tenant_id: str,
    operation: str,
    arguments: dict[str, Any],
    expected_effects: list[PredictedChange],
    policies: list[PolicyRule],
    process_id: str = "",
    risk_class: str = "low",
    external_parties: int = 0,
    affected_commitments: list[str] | None = None,
    trace_id: str = "",
) -> SimulationReport:
    context: dict[str, Any] = {
        "operation": operation,
        "source_id": operation.split(".")[0],
        "arguments": arguments,
        "process_id": process_id,
        "risk_class": risk_class,
        "target": {"region": arguments.get("region", "EU")},
    }
    violations = [v for rule in policies if (v := evaluate(rule, context)) is not None]
    blast = compute_blast_radius(expected_effects, arguments, external_parties)
    summary = describe(expected_effects, violations)
    return SimulationReport(
        action_id=action_id,
        tenant_id=tenant_id,
        changes=expected_effects,
        violations=violations,
        affected_commitments=affected_commitments or [],
        blast_radius=blast,
        summary=summary,
        trace_id=trace_id,
    )
