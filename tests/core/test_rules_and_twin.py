"""Policy engine and digital twin (spec 03, AT-03-1, AT-03-3, AT-03-4)."""

from __future__ import annotations

import pytest

from twin.engine import PredictedChange, describe, simulate, summary_mentions_only_diff
from twin.rules import PolicyRule, evaluate, lookup

SPEND = PolicyRule(
    id="POL-003",
    tenant_id="t",
    name="Spending above 10 000 SEK requires an approver",
    scope={"source_id": "accounting"},
    field="arguments.amount",
    operator="gt",
    value=10000,
    effect="require_approver",
)
RESIDENCY = PolicyRule(
    id="POL-007",
    tenant_id="t",
    name="Personal data must stay in the EU",
    field="target.region",
    operator="not_in",
    value=["EU"],
    effect="block",
)


def ctx(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "operation": "accounting.approve_invoice",
        "source_id": "accounting",
        "arguments": {"amount": 12400},
        "target": {"region": "EU"},
        "risk_class": "low",
    }
    base.update(kw)
    return base


def test_spending_rule_flags_the_right_rule_id() -> None:
    v = evaluate(SPEND, ctx())
    assert v is not None
    assert v.rule_id == "POL-003"
    assert v.effect == "require_approver"
    assert "12400" in v.evidence


def test_spending_rule_silent_below_the_limit() -> None:
    assert evaluate(SPEND, ctx(arguments={"amount": 400})) is None


def test_rule_out_of_scope_does_not_fire() -> None:
    """A spending limit has no business judging an action that carries no money."""
    out = ctx(source_id="clickup", operation="clickup.create_task", arguments={"title": "x"})
    assert evaluate(SPEND, out) is None


def test_absent_field_in_scope_fails_closed() -> None:
    v = evaluate(SPEND, ctx(arguments={}))
    assert v is not None
    assert v.effect == "require_approver"


def test_residency_rule_blocks_outside_eu() -> None:
    v = evaluate(RESIDENCY, ctx(target={"region": "us-east-1"}))
    assert v is not None
    assert v.effect == "block"


def test_disabled_rule_never_fires() -> None:
    assert evaluate(SPEND.model_copy(update={"enabled": False}), ctx()) is None


def test_lookup_never_touches_attributes() -> None:
    assert lookup({"a": {"b": 1}}, "a.b") == 1
    assert lookup({"a": {"b": 1}}, "a.__class__") is None
    assert lookup({"xs": [1, 2]}, "xs.1") == 2


@pytest.mark.parametrize("bad", ["__class__", "upper", "items"])
def test_lookup_rejects_python_internals(bad: str) -> None:
    assert lookup({"x": "s"}, f"x.{bad}") is None


def test_simulation_reports_violation_and_blast_radius() -> None:
    report = simulate(
        action_id="a1",
        tenant_id="t",
        operation="accounting.approve_invoice",
        arguments={"amount": 12400, "region": "EU"},
        expected_effects=[
            PredictedChange(kind="node", op="update", label_or_type="Record", key="inv:1")
        ],
        policies=[SPEND, RESIDENCY],
        risk_class="high",
        external_parties=1,
    )
    assert [v.rule_id for v in report.violations] == ["POL-003"]
    assert report.needs_approver
    assert not report.blocked
    assert 0.0 < report.blast_radius.normalised <= 1.0


def test_simulation_blocks_on_residency() -> None:
    report = simulate(
        action_id="a2",
        tenant_id="t",
        operation="gdrive.share_file",
        arguments={"region": "us-east-1"},
        expected_effects=[],
        policies=[RESIDENCY],
    )
    assert report.blocked


def test_summary_is_built_from_the_diff() -> None:
    changes = [PredictedChange(kind="node", op="create", label_or_type="Record", key="r:1")]
    assert "1 new" in describe(changes, [])
    assert summary_mentions_only_diff(describe(changes, []), changes)


def test_summary_naming_an_absent_entity_is_rejected() -> None:
    changes = [PredictedChange(kind="node", op="create", label_or_type="Record", key="r:1")]
    assert not summary_mentions_only_diff("It also updates record:ghost as a side effect.", changes)
