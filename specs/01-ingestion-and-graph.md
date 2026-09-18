# Spec 01 — Zero-schema ingestion and the knowledge graph (Pillar 1)

Status: draft (Phase 0) · Phase: 1 · Source: brief §5 Pillar 1, §2 principles 1, 2, 5, 6, 9

## Purpose

Connect to source systems through MCP adapters and build a knowledge graph without asking the
customer to define a schema up front. Plexus caches, indexes, and reasons over customer records
but never becomes a system of record (principle 5).

## Inputs

- Adapter output: a stream of `SourceItem`s (backfill) and `SourceEvent`s (watch), already
  tokenised by the PII Boundary (spec 06).
- Seed ontology (below) and any approved `OntologyProposal`s.
- Human corrections to previously extracted entities and relations.

## Outputs

- Graph nodes and edges in Neo4j (bitemporal, with provenance and status).
- Documents and chunks with embeddings in Postgres/pgvector for retrieval.
- `OntologyProposal` rows for labels/relationship types the seed ontology does not cover.
- Explain-agent answers with inline citations and the subgraph used.

## Data model changes

### Adapter contract (`adapters/_contract/base.py`)

```python
class AdapterCapabilities(BaseModel):
    read: bool = True
    write: bool = False  # generated adapters ship with this False (spec 08)
    watch: bool = False
    backfill: bool = True


class SourceRef(BaseModel):
    source_id: str  # adapter id, e.g. "gmail"
    external_id: str
    version: str | None = None
    url: str | None = None


class ActorRef(BaseModel):
    token: str  # tokenised person or system id, e.g. "<PERSON_7f3a>"
    kind: Literal["person", "system"]
    display_hint: str | None = None  # tokenised; never clear text


class SourceItem(BaseModel):
    tenant_id: str
    source_id: str
    external_id: str
    kind: Literal["email", "message", "task", "file", "record"]
    title: str
    body: str
    structured: dict[str, Any]
    actors: list[ActorRef]
    created_at: datetime
    updated_at: datetime | None
    raw_ref: SourceRef


class SourceEvent(BaseModel):  # near-real-time change notification
    tenant_id: str
    source_id: str
    ref: SourceRef
    change: Literal["created", "updated", "deleted"]
    ts: datetime


class WriteOp(BaseModel):  # only constructed by core/action/executor.py
    tenant_id: str
    source_id: str
    operation: str  # adapter-defined, e.g. "clickup.set_status"
    arguments: dict[str, Any]  # restored (clear text) inside executor only
    idempotency_key: str


class WriteResult(BaseModel):
    ok: bool
    ref: SourceRef | None
    reversal: WriteOp | None  # how to undo, if the adapter supports it
    message: str | None


class SourceSchema(BaseModel):
    fields: list[FieldSpec]  # name, type, id?, pii_hint?
    record_types: list[str]


class PlexusAdapter(Protocol):
    id: str
    capabilities: AdapterCapabilities

    async def backfill(self, since: datetime | None) -> AsyncIterator[SourceItem]: ...
    async def watch(self) -> AsyncIterator[SourceEvent]: ...
    async def read(self, ref: SourceRef) -> SourceItem: ...
    async def write(self, op: WriteOp) -> WriteResult: ...  # ONLY callable from executor
    def describe_schema(self) -> SourceSchema: ...
```

Every `SourceItem` passes through the PII Boundary before leaving the adapter process; the
adapter base class enforces this in `_emit()`, adapters cannot bypass it.

### Seed ontology

Node labels: `Person`, `Organisation`, `Project`, `Event`, `Session`, `Concept`, `Artifact`,
`Publication`, `Method`, `Question`, `Process`, `ProcessStep`, `Decision`, `Policy`,
`Commitment`, `Record` (generic; has `source` and `record_type`).

Relationship types: `WORKS_AT`, `MEMBER_OF`, `OWNS`, `PARTICIPATED_IN`, `PRODUCED`, `MENTIONS`,
`DEPENDS_ON`, `FOLLOWS`, `DECIDED_IN`, `GOVERNED_BY`, `COMMITTED_TO`, `SAME_AS`, `DERIVED_FROM`.

Common properties on every node and edge: `id`, `tenant_id`, `created_at`, `valid_from`,
`valid_to`, `confidence`, `provenance: list[SourceRef]` (stored as JSON string in Neo4j),
`status: proposed|confirmed|rejected`, `erased: bool` (GDPR, spec 06).

The ontology is data (`core/graph/schema.py` exports it as Pydantic models) so that approved
proposals extend it without code changes. Changing the seed ontology after Phase 1 requires
sign-off (brief §0.5b).

### Postgres tables (Phase 1 migration)

- `documents(id, tenant_id, source_ref jsonb, kind, title, body_tokenised, structured jsonb,
  created_at, updated_at, erased)`
- `chunks(id, tenant_id, document_id, ordinal, text_tokenised, embedding vector(1024))`
- `ontology_proposals(id, tenant_id, kind label|relationship|verb, name, rationale, examples
  jsonb, status pending|approved|rejected, decided_by, decided_at)`
- `corrections(id, tenant_id, target_kind, target_id, original jsonb, corrected jsonb, author,
  created_at, reason)`
- Row-level security on every table keyed by `current_setting('plexus.tenant_id')`.

### Graph store abstraction (`core/graph/store.py`)

```python
class GraphStore(Protocol):
    async def apply(self, delta: GraphDelta) -> AppliedDelta
    async def query(self, tenant_id: str, cypher: str, params: dict) -> list[Record]
    async def snapshot(self, tenant_id: str, scope: SnapshotScope) -> GraphSnapshot  # for twin
```

`query` rejects any Cypher that does not bind `$tenant_id` and reference it in every `MATCH`
(a conservative static check; raw Cypher from agents is rejected otherwise). Implementations:
`Neo4jStore` (prod), `KuzuStore` (embedded, unit tests).

## Interfaces

### Extraction agent (`agents/extract/`)

1. `propose_mentions(item: SourceItem) -> MentionSet` — strict JSON via router
   `complete(role="workhorse", schema=MentionSet)`, one retry on invalid output.
2. `resolve(mentions: MentionSet, store: GraphStore) -> ResolvedSet` — exact id match, then
   embedding similarity above `config.extract.similarity_threshold`, then LLM adjudication only
   for the top-3 ambiguous candidates. Emits `SAME_AS` with confidence; never merges nodes.
3. `propose_ontology(unfit: list[Mention]) -> list[OntologyProposal]`.
4. Returns a `GraphDelta`; `core/graph/apply.py` applies it (agents never write to the store).

### Explain agent (`agents/explain/`)

`explain(tenant_id, question: str) -> Answer` where `Answer = {text, citations: list[SourceRef],
subgraph: GraphSnapshot, trace_id}`. Steps: plan (Cypher + vector query), execute via
`GraphStore.query` and `documents.search`, answer with inline `[n]` citations bound to
`provenance` refs.

### API (`/v1`)

- `POST /v1/tenants/{t}/ingest/backfill` `{source_id, since?}` → starts a Temporal workflow.
- `GET /v1/tenants/{t}/graph/nodes?label=&q=` and `GET .../graph/nodes/{id}` (with provenance).
- `GET /v1/tenants/{t}/ontology/proposals`, `POST .../ontology/proposals/{id}:approve|reject`
  (role `operator`+).
- `POST /v1/tenants/{t}/ask` `{question}` → `Answer`.
- `POST /v1/tenants/{t}/corrections` → stored correction; applies a closing/opening delta.

### Temporal

`BackfillWorkflow(tenant_id, source_id, since)`: activities `list_items`, `extract_item`,
`apply_delta`, with per-item retries and a heartbeat. No bare loops (principle 7).

## Failure modes

| Failure | Behaviour |
|---|---|
| Adapter unreachable | Workflow retries with backoff; item marked `pending`; health shows adapter down. |
| Model returns invalid JSON twice | Item parked in `extraction_failures`, surfaced in dashboard; no partial delta applied. |
| Entity resolution ambiguous | `SAME_AS` with confidence < threshold stays `proposed`; never merged. |
| Ontology does not fit | `OntologyProposal` created; mentions stored under `Record` with `record_type` meanwhile. |
| Cypher without tenant predicate | `GraphStore.query` raises `TenantPredicateMissing`; span tagged; never executed. |
| PII found in a model request (fuzz) | Release blocker; CI fails. |

## Acceptance tests

- AT-01-1: Backfill fixtures (500 emails, 200 tasks, 100 files) → graph precision ≥ 90% on the
  hand-labelled 100-item entity set in `scripts/fixtures/labels/entities.jsonl`.
- AT-01-2: "Which people were involved in project X and what did they commit to?" returns an
  answer citing ≥ 3 sources across ≥ 2 adapters.
- AT-01-3: Zero clear-text PII in any model request log (hypothesis fuzz over the boundary, plus
  grep of request logs after the demo run).
- AT-01-4: `GraphStore.query` rejects Cypher without a tenant predicate (unit).
- AT-01-5: Applying a delta that contradicts an existing fact closes the old fact (`valid_to`
  set) and opens the new; the old row is still queryable as-of its interval.
- AT-01-6: Adapter conformance suite passes for gmail, clickup, gdrive against fixtures.

## Open questions

- OQ-01-1: Embedding dimension. `bge-m3` is 1024; the Anthropic-recommended provider may differ.
  Recommendation: fix `vector(1024)` for the pilot and project other models to 1024 if needed,
  since changing the column later is a migration on a small table.
- OQ-01-2: Should Kùzu be used for unit tests at all, given Neo4j testcontainers are cheap on a
  laptop? Recommendation: keep Kùzu for pure-Python unit tests (fast CI) and run the conformance
  suite against Neo4j in `test-integration`.
- OQ-01-3: MCP transport for adapters in compose: stdio (one process per adapter, supervised by
  the API) or streamable HTTP (one container each). Recommendation: streamable HTTP in compose
  from day one so deployment and dev are the same shape.
