# Spec 00 — Glossary and shared conventions

Status: draft (Phase 0) · Owner: core · Source: docs/product-brief.md §1–§3, §7

## Purpose

Define the vocabulary every other spec uses, and the cross-cutting conventions (identifiers,
time, tenancy, status values, confidence) so that no spec has to redefine them.

## Terms

| Term | Definition |
|---|---|
| **Tenant** | One customer installation. Every row, node, edge, stream key, span, and log line carries `tenant_id`. |
| **Source system** | A customer tool Plexus reads from (and may later write to): Gmail, ClickUp, Drive, Slack, a Postgres database. |
| **Adapter** | An MCP server implementing `PlexusAdapter` for one source system. Runs as its own process. |
| **SourceItem** | One unit of content pulled from a source system (email, message, task, file, record). Tokenised before it leaves the adapter process. |
| **SourceRef** | A stable pointer `{source_id, external_id, version?, url?}` back to a record in a source system. Used for provenance and citations. |
| **PII Boundary** | `core/pii/boundary.py`. The only place clear-text personal data is turned into tokens (and back, inside the executor). |
| **Token** | A format-preserving, per-tenant-stable placeholder such as `<PERSON_7f3a>` that replaces a PII value. |
| **Token vault** | Encrypted Postgres table mapping tokens to real values. The only place real values live. |
| **Knowledge graph** | Neo4j graph of entities and relationships extracted from source items, bitemporal, with provenance. |
| **GraphDelta** | A list of proposed node/edge upserts with provenance and confidence, produced by agents and applied only by `core/graph/apply.py`. |
| **PlexusEvent** | One object-centric event in the unified event model: actor, verb, objects, source, attributes. |
| **Event synthesiser** | Agent that turns unstructured threads into `PlexusEvent`s using the fixed verb vocabulary. |
| **Case** | A group of events sharing object ids, the unit process mining runs over. |
| **Process** | A discovered workflow: `Process` node, ordered `ProcessStep` nodes with `FOLLOWS` edges, plus metrics. |
| **Digital twin** | Simulation engine that applies a `ProposedAction` to a copy of the graph and reports predicted consequences. |
| **Shadow mode** | Running plan → simulate on real events for a process at a tier that cannot act, recording what would have happened. |
| **Autonomy Ledger** | Append-only, hash-chained table of every shadow run, suggestion, approval, rejection, execution, reversal, promotion, demotion, and override, per process. |
| **Trust score** | Per-process number in `[0, 1]` computed from the ledger by the formula in spec 04. |
| **Tier** | One of `OBSERVE`, `EXPLAIN`, `SUGGEST`, `ACT_WITH_APPROVAL`, `AUTONOMOUS`, per process. |
| **Actor** | The model role that proposes actions (`agents/plan/`). |
| **Verifier** | The model role, from a different vendor, that judges proposals (`agents/verify/`). Cannot modify a proposal. |
| **Workhorse** | The model role for extraction, summarisation, event synthesis. |
| **Classifier** | The cheap model role for routing and labelling. |
| **Embedder** | The embedding model role (multilingual; Swedish + English). |
| **ProposedAction** | Actor output: target adapter, operation, arguments, rationale, cited graph refs, expected effects, self-declared risk class. |
| **SimulationReport** | Twin output: predicted diff, policy violations, affected commitments, plain-language summary derived only from the diff. |
| **Verdict** | Verifier output: `approve`, `reject`, or `escalate`, with reasons mapped to policy ids or graph facts. |
| **Executor** | `core/action/executor.py`. The only module allowed to call adapter write methods and the only place tokens are restored. |
| **Policy** | A structured rule (`field`, `operator`, `value`, `scope`) attached to nodes via `GOVERNED_BY`. Evaluated by the safe rule engine, never `eval`. |
| **OntologyProposal** | A proposed new node label, relationship type, or event verb awaiting human approval. |
| **Correction** | A human edit to an extracted entity, relation, step, variant, or action, stored alongside the original as training data. |
| **Kill switch** | Tenant-level and process-level `paused` flags checked by the executor on every action. |
| **Sandbox tenant** | A tenant that mirrors the real adapters with fixture data, used exclusively by the immune system. |
| **Immune score** | Dashboard metric summarising the red/blue team results over time. |
| **Nordvik Konsult AB** | The fictional 12-person company in `scripts/fixtures/` that all acceptance tests and demos run against. |

## Conventions

### Identifiers
- All ids are strings. Plexus-generated ids are UUIDv7 (time-ordered, sortable), rendered as
  lower-case hex with hyphens.
- External ids are kept verbatim from the source system inside a `SourceRef`; never used as a
  Plexus primary key on their own.
- `tenant_id` is a short slug (`tcl`, `nordvik`, `sandbox-nordvik`), validated by
  `^[a-z0-9][a-z0-9-]{1,62}$`.

### Time
- All timestamps are timezone-aware UTC `datetime`s in Python and `timestamptz` in Postgres.
- Bitemporal fields on graph nodes/edges: `created_at` (when Plexus learned it), `valid_from` /
  `valid_to` (when it was true in the world). `valid_to = null` means currently valid.
  Facts are never overwritten: close the old (`valid_to = now`) and open the new.

### Status and confidence
- Graph `status`: `proposed | confirmed | rejected`. Agents produce `proposed`; humans or
  high-confidence rules produce `confirmed`; humans produce `rejected`.
- `confidence` is a float in `[0, 1]`. Deterministic sources (a structured field from an adapter)
  are `1.0`. Model outputs carry the model's self-reported confidence, calibrated later by evals.

### Naming
- Python: `snake_case` modules and functions, `PascalCase` classes, `UPPER_SNAKE` constants.
- Node labels: `PascalCase`. Relationship types and event verbs: `UPPER_SNAKE` for relationships,
  `lower_snake` for verbs.
- Env vars: `PLEXUS_*` for Plexus settings; vendor-standard names (`ANTHROPIC_API_KEY`) otherwise.

### Errors
- Domain errors subclass `PlexusError` (`core/errors.py`, Phase 1). Never raise bare `Exception`.
- Anything crossing a process boundary (API, Temporal activity, MCP) returns typed Pydantic
  models; no `dict` payloads without a schema.

### Tracing
- Every span carries `tenant_id`, `process_id` (when applicable), `tier` (when applicable),
  `trace_id`. Ledger entries and model-call cost rows store the `trace_id`.

## Open questions

- OQ-00-1: Should `tenant_id` be a UUID rather than a slug for easier rotation? Recommendation:
  slug for pilot (human-readable in logs), add a `tenants` table with a UUID `id` alongside so a
  rename is cheap later.
