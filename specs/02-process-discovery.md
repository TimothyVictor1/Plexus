# Spec 02 — Process discovery from communication (Pillar 2)

Status: draft (Phase 0) · Phase: 2 · Source: brief §5 Pillar 2

## Purpose

Mine real workflows from unstructured communication and structured record changes without
pre-existing event logs, and represent them as `Process`/`ProcessStep` graphs with metrics.

## Inputs

- `PlexusEvent`s emitted by adapters for structured changes (status change, file created).
- Tokenised threads (email, chat) for the event synthesiser.
- Human corrections: variant merges, step renames, step splits.

## Outputs

- Rows in the Postgres `event_log` table (object-centric, OCEL 2.0-compatible in spirit).
- `Process`, `ProcessStep` nodes with `FOLLOWS` edges and metrics.
- One Autonomy Ledger entry per discovered process, tier `OBSERVE` (spec 04).
- `OntologyProposal`s for new verbs.

## Data model changes

### Unified event model (`core/events/model.py`)

```python
class ObjectRef(BaseModel):
    object_type: str  # "task", "thread", "quote", "invoice", "person" ...
    object_id: str  # tokenised where it identifies a person
    source: SourceRef | None


class PlexusEvent(BaseModel):
    tenant_id: str
    event_id: str
    ts: datetime
    actor: ActorRef
    verb: str  # must be in core/events/verbs.py or an approved proposal
    objects: list[ObjectRef]
    source: SourceRef
    attributes: dict[str, Any]
    confidence: float = 1.0  # 1.0 for structured, model-reported for synthesised
    synthesised: bool = False
```

### Verb vocabulary (`core/events/verbs.py`)

Initial fixed set: `sent`, `replied`, `forwarded`, `created`, `updated`, `deleted`,
`changed_status`, `assigned`, `attached`, `commented`, `requested`, `offered`, `accepted`,
`rejected`, `approved`, `paid`, `invoiced`, `scheduled`, `attended`, `published`, `decided`,
`committed`. The model may propose new verbs only via `OntologyProposal(kind="verb")`.

### Postgres

- `event_log(event_id, tenant_id, ts, actor jsonb, verb, objects jsonb, source jsonb,
  attributes jsonb, confidence, synthesised, trace_id)` with a GIN index on `objects` and RLS.
- `process_variants(id, tenant_id, process_id, signature text, count, merged_into)`.
- `corrections` (spec 01) gains `target_kind in ('variant_merge','step_rename','step_split')`.
- Redis stream `events:{tenant_id}` carries events from adapters to the synthesiser/miner.

### Graph

- `Process {name, description, metrics: json, tier, discovered_at, version}`
- `ProcessStep {name, verb_set, frequency, median_duration_s, actors_per_step, ordinal}`
- `(:ProcessStep)-[:FOLLOWS {count, median_gap_s}]->(:ProcessStep)`
- `(:Process)-[:OWNS]->(:ProcessStep)`

## Interfaces

### Event synthesiser (`agents/discover/synthesise.py`)

`synthesise(thread: list[SourceItem]) -> list[PlexusEvent]` via router role `workhorse`,
schema-validated, verbs restricted to the vocabulary (invalid verb → retry once with the
vocabulary restated, then park with an `OntologyProposal`).

### Discovery agent (`agents/discover/`)

1. `build_cases(events) -> list[Case]` — group by shared object ids (union-find over object
   references; one case per connected component within a time window).
2. `mine(cases) -> DFG` — deterministic directly-follows graph plus a heuristic miner in pure
   Python (`agents/discover/miner.py`): dependency measure, thresholds from config.
3. `label(dfg) -> LabelledProcess` — model names the process, labels steps in plain language, and
   proposes which variants are the same step phrased differently. Output is a proposal; the
   deterministic structure is never altered by the model.
4. `emit(labelled) -> GraphDelta` + metrics (median cycle time, step frequency, bottleneck,
   actors per step, variant count).

### API

- `GET /v1/tenants/{t}/processes`, `GET .../processes/{id}` (steps, metrics, variants, tier).
- `POST .../processes/{id}/variants:merge` `{from, into}` (role `operator`+) → correction row;
  the miner reads corrections on re-run.
- `POST .../processes:rediscover` → Temporal `DiscoveryWorkflow`.
- `GET .../events?object_id=&verb=&since=` and `GET .../events:export?format=ocel2`.

### Temporal

`DiscoveryWorkflow(tenant_id)` runs nightly and on demand: activities `load_events`,
`synthesise_batch`, `mine`, `label`, `apply_delta`, `ledger_register_process`.

## Failure modes

| Failure | Behaviour |
|---|---|
| Verb outside vocabulary after retry | Event parked; `OntologyProposal(kind="verb")` created. |
| No cases found | Workflow completes with `processes_found = 0`; dashboard shows "not enough data". |
| Model labelling fails | Process is emitted with generated names (`Step 1..n`), flagged `needs_labels`. |
| Correction conflicts with new mining | Correction wins; conflict logged for review. |

## Acceptance tests

- AT-02-1: From fixtures containing "customer enquiry → quote → acceptance → invoice" spread
  across Gmail and ClickUp, the miner discovers a 4–6 step process with correct ordering and a
  cycle time within 10% of `scripts/fixtures/labels/processes.json`.
- AT-02-2: A human merges two variants in the dashboard; the merge is stored as a correction and
  the miner respects it on re-run.
- AT-02-3: Every discovered process has exactly one `promotion`-type ledger entry at `OBSERVE`.
- AT-02-4: Synthesised events never contain a verb outside the vocabulary (property test over
  parsed outputs).
- AT-02-5: OCEL 2.0 export round-trips through a JSON schema check.

## Open questions

- OQ-02-1: Case-window size (how long two events may be apart and still be one case).
  Recommendation: 45 days default, configurable per tenant.
- OQ-02-2: Whether to import `pm4py` for validation of the pure-Python miner in tests only.
  Recommendation: yes in `dev` dependencies only, never at runtime, so the miner is checked
  against a reference implementation.
