"""Safe policy rule engine (spec 03).

A small interpreter over a fixed operator set. No eval, no exec, no attribute access: values
are looked up by dotted path on plain dicts only.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

Operator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "matches", "between"]
Effect = Literal["require_approver", "block", "warn", "require_working_hours", "data_residency"]


class PolicyRule(BaseModel):
    id: str
    tenant_id: str
    name: str
    scope: dict[str, Any] = Field(default_factory=dict)
    field: str
    operator: Operator
    value: Any
    effect: Effect
    enabled: bool = True
    version: int = 1


class PolicyViolation(BaseModel):
    rule_id: str
    rule_name: str
    effect: Effect
    evidence: str


def lookup(data: dict[str, Any], path: str) -> Any:
    """Dotted lookup over dicts and list indices. Never touches attributes."""
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            current = current[idx] if idx < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(" ", "").replace(",", "."))
        except ValueError:
            return None
    return None


def evaluate(rule: PolicyRule, context: dict[str, Any]) -> PolicyViolation | None:
    if not rule.enabled:
        return None
    if not _in_scope(rule, context):
        return None

    actual = lookup(context, rule.field)
    if actual is None:
        # Fail closed: a rule that cannot be evaluated becomes an approver requirement.
        return PolicyViolation(
            rule_id=rule.id,
            rule_name=rule.name,
            effect="require_approver",
            evidence=f"field {rule.field} is absent, so the rule could not be evaluated",
        )

    triggered = _compare(rule.operator, actual, rule.value)
    if not triggered:
        return None
    return PolicyViolation(
        rule_id=rule.id,
        rule_name=rule.name,
        effect=rule.effect,
        evidence=f"{rule.field} = {actual!r} {rule.operator} {rule.value!r}",
    )


def _in_scope(rule: PolicyRule, context: dict[str, Any]) -> bool:
    for key, expected in rule.scope.items():
        if expected in (None, "", "*"):
            continue
        if lookup(context, key) != expected:
            return False
    return True


def _compare(op: Operator, actual: Any, expected: Any) -> bool:
    if op == "eq":
        return bool(actual == expected)
    if op == "ne":
        return bool(actual != expected)
    if op in {"gt", "gte", "lt", "lte"}:
        a, b = _as_number(actual), _as_number(expected)
        if a is None or b is None:
            return False
        return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]
    if op == "in":
        return isinstance(expected, list) and actual in expected
    if op == "not_in":
        return isinstance(expected, list) and actual not in expected
    if op == "matches":
        return bool(re.search(str(expected), str(actual)))
    if op == "between":
        a = _as_number(actual)
        if a is None or not isinstance(expected, list) or len(expected) != 2:
            return False
        lo, hi = _as_number(expected[0]), _as_number(expected[1])
        return lo is not None and hi is not None and not (lo <= a <= hi)
    return False
