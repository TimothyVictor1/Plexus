# Spec 05 — Actor / Verifier separation of duties (Pillar 5)

Status: draft (Phase 0) · Phase: 3 · Source: brief §5 Pillar 5, §2 principles 1 and 3

## Purpose

No single model proposes and approves the same action. The Action Pipeline
(plan → simulate → verify → approve/auto → execute → record) is the only write path.

## Inputs

- Triggering `PlexusEvent`, the matched `Process`, and graph context (subgraph + retrieved
  documents, all tokenised).
- `SimulationReport` (spec 03), applicable `PolicyRule`s, recent ledger entries for the process.
- Tier and pause flags (spec 04).

## Outputs

- `ProposedAction`, `Verdict`, and (where allowed) a `WriteResult`, each recorded in the ledger.
- Inbox items for humans at `SUGGEST` and `ACT_WITH_APPROVAL`; post-hoc notifications with
  one-click reversal at `AUTONOMOUS`.

## Data model changes

```python
class ProposedAction(BaseModel):
    id: str
    tenant_id: str
    process_id: str
    trigger_event_id: str
    target_source_id: str  # adapter id
    operation: str
    arguments: dict[str, Any]  # tokenised
    rationale: str
    cited_context: list[GraphRef]  # node/edge ids + SourceRefs
    expected_effects: list[PredictedChange]
    risk_class: Literal["low", "medium", "high"]
    actor_model: ModelId  # vendor + model + prompt version
    trace_id: str


class Verdict(BaseModel):
    action_id: str
    decision: Literal["approve", "reject", "escalate"]
    reasons: list[VerdictReason]  # {kind: policy|graph_fact|simulation|uncertainty, ref, text}
    verifier_model: ModelId  # vendor MUST differ from actor_model.vendor
    trace_id: str
```

Postgres: `proposed_actions`, `verdicts` (with `UNIQUE(action_id)`), `executions(action_id
REFERENCES proposed_actions, verdict_id NOT NULL REFERENCES verdicts, approver jsonb,
write_result jsonb, reversal jsonb, ts)`. The `NOT NULL` foreign key is the structural guarantee
that no execution exists without a stored verdict.

## Interfaces

### Actor (`agents/plan/`)

`plan(ctx: PlanContext) -> ProposedAction` via router role `actor`, schema-validated. The prompt
(`prompts/actor.md`) requires citations for every claim in `rationale` and forbids operations
not in the adapter's declared write operations.

### Verifier (`agents/verify/`)

`verify(action, report, policies, ledger_tail) -> Verdict` via router role `verifier`. The prompt
(`prompts/verifier.md`) is adversarial: "assume the proposal is wrong; find why". The verifier
receives no tool that can change the proposal; the return schema has no free-form
`modified_action` field.

### Executor (`core/action/executor.py`)

```python
async def execute(action: ProposedAction, verdict: Verdict, approval: HumanApproval | None) -> ExecutionRecord
```
Order of checks, all before any restore or write:
1. Tenant and process `paused` flags → refuse (ledger `refusal`).
2. Tier rules: `SUGGEST` → refuse; `ACT_WITH_APPROVAL` → require `verdict.approve` and
   `approval.role == approver`; `AUTONOMOUS` → require `verdict.approve`; `escalate` → refuse
   and open an Inbox item.
3. Adapter `capabilities.write` is true and `operation` is in its allow-list.
4. Restore tokens (spec 06) immediately before `adapter.write`; restored payload is never logged.
5. Write; record `execution` (and `reversal` op if returned); notify.

The only module allowed to import `write` from an adapter is this file; enforced by
`tests/architecture/test_import_boundaries.py`.

### Temporal

`ActionWorkflow(tenant_id, process_id, event_id)`: activities `plan`, `simulate`, `verify`,
`await_approval` (signal, with timeout → expire), `execute`, `notify`, `record`. Waiting on a
human is a Temporal signal, never a poll.

### API

- `GET /v1/tenants/{t}/inbox` → items with proposal, report, verdict.
- `POST .../inbox/{id}:approve|reject` (role `approver`) → signal to the workflow.
- `POST .../executions/{id}:reverse` (role `approver`) → executes the stored reversal op through
  the same executor and records `reversal` (which demotes, spec 04).

## Failure modes

| Failure | Behaviour |
|---|---|
| Actor and verifier resolve to the same vendor in production | Router refuses to boot (spec 09). |
| Verifier unreachable | Action stays pending; no fallback to a same-vendor verifier ever. |
| Verdict `escalate` | Always routed to a human regardless of tier. |
| Adapter write fails after restore | `execution` entry with `ok=false`; restored payload not logged; retry only with the same idempotency key. |
| Approval timeout | Inbox item expires; ledger `rejection` with `reason=expired`. |

## Acceptance tests

- AT-05-1: Router refuses to boot in `env=production` if `actor.vendor == verifier.vendor`.
- AT-05-2: ≥ 95% of 100 seeded adversarial proposals (`evals/adversarial/`) that violate a
  policy are rejected by the verifier.
- AT-05-3: No execution without a stored verdict (DB constraint test + executor unit test).
- AT-05-4: At `SUGGEST` tier the executor never calls `adapter.write` (call count = 0).
- AT-05-5: A full approve → execute → reverse cycle is visible in the ledger with a valid chain
  and ends with a demotion entry.

## Open questions

- OQ-05-1: Should `AUTONOMOUS` be allowed for `risk_class = high` at all? Recommendation: no;
  cap high-risk actions at `ACT_WITH_APPROVAL` regardless of trust, configurable per tenant.
