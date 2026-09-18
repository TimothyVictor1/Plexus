# Spec 03 — Digital twin and shadow mode (Pillar 3)

Status: draft (Phase 0) · Phase: 2 · Source: brief §5 Pillar 3

## Purpose

Simulate a proposed action against a copy of the graph before it is taken, report predicted
consequences and policy violations, and run that simulation in shadow mode for processes that
cannot yet act so trust is earned before any real write.

## Inputs

- `ProposedAction` (spec 05) and a `GraphSnapshot` (spec 01, scoped to the action's objects and
  their neighbourhood up to depth `config.twin.snapshot_depth`).
- Policies attached via `GOVERNED_BY` edges, as structured rules.
- Real events (shadow mode): every `PlexusEvent` matched to a process at `OBSERVE`/`EXPLAIN`.

## Outputs

- `SimulationReport`.
- Ledger entries of type `shadow_run` (spec 04) with the report as payload.
- Zero writes to any adapter (asserted by executor call count).

## Data model changes

```python
class PolicyRule(BaseModel):
    id: str
    tenant_id: str
    name: str
    scope: RuleScope  # {label?, process_id?, source_id?}
    field: str  # dotted path into the action or affected node, e.g. "arguments.amount"
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "matches", "between"]
    value: Any
    effect: Literal["require_approver", "block", "warn", "require_working_hours", "data_residency"]
    enabled: bool = True
    version: int


class PredictedChange(BaseModel):
    kind: Literal["node", "edge"]
    op: Literal["create", "update", "close"]
    label_or_type: str
    id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class SimulationReport(BaseModel):
    action_id: str
    tenant_id: str
    changes: list[PredictedChange]
    violations: list[PolicyViolation]  # {rule_id, effect, evidence}
    affected_commitments: list[str]  # Commitment node ids
    blast_radius: (
        BlastRadius  # records_touched, money_touched, external_parties_touched, normalised 0..1
    )
    summary: str  # model-written from the structured diff ONLY
    trace_id: str
```

Postgres: `policies` (rules, versioned; RLS), `simulations(id, tenant_id, action_id, report
jsonb, ts, trace_id)`.

Initial policy library (seeded per tenant, editable in dashboard): spending limit
(`arguments.amount gt 10000 → require_approver`), approval requirement by record type,
data-residency (`target.region not_in ["EU"] → block`), working hours (`ts.hour between 8..18 →
otherwise require_approver`).

## Interfaces

- `twin/engine.py`: `simulate(action: ProposedAction, snapshot: GraphSnapshot, policies:
  list[PolicyRule]) -> SimulationReport`. Applies the action's expected effects to an in-memory
  copy of the snapshot, never the live store.
- `twin/rules.py`: `evaluate(rule: PolicyRule, context: dict) -> Violation | None`. A small
  interpreter over the operator enum; no `eval`, no attribute access beyond dotted lookups on
  plain dicts.
- `twin/summarise.py`: builds the model prompt from `changes` + `violations` only, router role
  `workhorse`, and post-checks that every entity mentioned in the summary appears in the diff.
- `workflows/shadow.py`: `ShadowRunWorkflow(tenant_id, process_id, event_id)` → plan (spec 05)
  → simulate → ledger `shadow_run`. Started by the event router for processes at `OBSERVE` or
  `EXPLAIN` tier.
- API: `GET/POST/PUT /v1/tenants/{t}/policies` (role `approver`+ to enable/disable), `GET
  /v1/tenants/{t}/simulations/{id}`.

## Failure modes

| Failure | Behaviour |
|---|---|
| Snapshot too large | Depth reduced by one and retried; report flagged `partial_snapshot`. |
| Rule references unknown field | Violation of kind `rule_error`, effect `require_approver` (fail closed). |
| Summary mentions an entity not in the diff | Summary replaced with a deterministic template; incident counted in evals. |
| Shadow run attempts a write | Impossible by construction (executor not imported); integration test asserts count = 0. |

## Acceptance tests

- AT-03-1: "approve invoice" with `amount = 12 000 SEK` against the rule "amount > 10 000 SEK
  requires approver" is flagged with that rule's id.
- AT-03-2: Shadow runs on 50 seeded events produce 50 reports and zero adapter writes.
- AT-03-3: The rule engine rejects any operator not in the enum and never calls `eval`
  (static test greps `twin/` for `eval(`/`exec(`).
- AT-03-4: The summary post-check rejects a crafted summary that names an entity absent from
  the diff.

## Open questions

- OQ-03-1: Should shadow runs also call the verifier (spec 05) so its verdict history feeds
  trust before any real action? Recommendation: yes from `EXPLAIN` tier upward; it doubles model
  cost for shadow runs, so gate it on config `twin.shadow_verify`.
