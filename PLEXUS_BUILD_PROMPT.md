# PLEXUS — Build Brief for Claude Code

You are the lead engineer building **Plexus**, an organisational nervous system: a system-agnostic intelligence layer that plugs into a company's existing tools, learns how the company actually works, and gradually earns the right to act inside those tools as an autonomous agent.

Read this entire document before writing a single line of code. Then follow the **Working Method** section. This brief is the source of truth. When the brief is silent, choose the option that is simplest, most auditable, and most reversible.

---

## 0. How to use this brief

1. On first run: copy the section **"CLAUDE.md contents"** at the bottom into `./CLAUDE.md` so every future session starts with the rules loaded.
2. Create the repo skeleton described in section 4.
3. Turn each pillar in section 5 into a file under `specs/` before implementing it. Specs are written first, reviewed, then implemented. Never implement from memory of this brief; implement from the spec file.
4. Build in the phase order in section 9. Do not start a phase until the previous phase's Definition of Done passes in CI.
5. Ask me before any decision that (a) adds a paid external dependency, (b) changes the graph schema after Phase 1, (c) touches the write path to customer systems, or (d) changes the Autonomy Ledger formula.

---

## 1. Product vision

**Problem.** Companies with 20 to 500 employees run on email, chat, a CRM, a ticketing tool, shared drives, and a few databases. Their processes are not documented anywhere; they live in people's heads and inboxes. Existing AI agent platforms either lock into one vendor's ecosystem (Copilot Studio, Agentforce, ServiceNow) or need enterprise budgets and months of data engineering (Celonis, Palantir). Nobody offers a plug-in layer that builds the company's own operational map automatically and then acts on it with provable, earned autonomy.

**Solution.** Plexus connects to whatever the company already runs through MCP adapters, builds a living knowledge graph plus a process graph from both structured records and unstructured communication, simulates actions before taking them, and promotes each process up an autonomy ladder only when its track record justifies it. Every action is verified by a second model from a different vendor, every PII field is tokenised before a model sees it, and the system continuously red-teams its own inputs.

**Customer zero** is Tech Concept Lab (TCL) in Karlskrona. Pilot two is a Blue Science Park company. Design for EU hosting, GDPR, and the EU AI Act from day one.

**One-sentence pitch:** Palantir and Celonis outcomes for mid-size European companies, installed in a day, where autonomy is earned rather than switched on.

---

## 2. Non-negotiable architecture principles

These are rules, not preferences. Violating one is a bug.

1. **Read is free, write is earned.** Any code path that writes to a customer system must go through the Action Pipeline (plan → simulate → verify → approve/auto → execute → record). There is no other write path. Enforce this structurally: the only module allowed to import adapter write methods is `core/action/executor.py`.
2. **PII never reaches a model in clear text.** Every byte that leaves an adapter passes through the PII Boundary (Presidio). Tokens are restored only inside the executor at write-back time. Test this with a fuzz suite; a single leak is a release blocker.
3. **Two-model separation of duties.** The Actor and the Verifier are configured to different model vendors. The Verifier's approval is required for every Act-tier or Autonomous-tier execution. The router must refuse to start if actor and verifier resolve to the same vendor in production config.
4. **Everything is traced.** Every model call, tool call, graph mutation, and action carries a trace ID (OpenTelemetry). The Autonomy Ledger is append-only. Nothing is deleted from the ledger; corrections are new entries.
5. **Graph is the source of truth for context; source systems are the source of truth for records.** Plexus never becomes a system of record. It caches, indexes, and reasons; it does not own customer data.
6. **Human corrections are training data.** Every time a human corrects an extracted entity, relationship, process step, or action, the correction is stored with the original so the extraction prompts and evals can improve.
7. **Durable by default.** Any workflow that can wait on a human, an external system, or a timer runs inside Temporal. No agent loop lives in a bare `while True`.
8. **Local first.** The full system runs on one developer laptop with `docker compose up`. No cloud dependency is required for development or for the TCL pilot.
9. **Model-agnostic.** All model calls go through `core/models/router.py`. No file outside that module imports a vendor SDK.
10. **Specs before code.** No implementation PR without a corresponding `specs/*.md` file and acceptance tests derived from it.

---

## 3. Technology stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 (backend), TypeScript (dashboard) | uv for Python deps, pnpm for TS |
| API | FastAPI + Pydantic v2 | OpenAPI generated, versioned under `/v1` |
| Durable workflows | Temporal (self-hosted via compose) | one workflow per process instance |
| Graph store | Neo4j 5 Community (prod), Kùzu embedded (unit tests) | Cypher; abstract behind `core/graph/store.py` |
| Document + vector store | PostgreSQL 16 + pgvector | documents, chunks, embeddings, corrections |
| Queue / cache / sessions | Redis 7 | Streams for events, plain keys for sessions |
| PII | Microsoft Presidio (analyzer + anonymizer) | custom recognisers for Swedish personnummer, org-nr, IBAN, phone |
| Adapters | MCP (Python SDK), one server per integration | stdio for local, streamable HTTP for deployed |
| Models | Anthropic (actor/workhorse), OpenAI or Google (verifier), Ollama/vLLM (sovereign open-weight option) | see section 6 |
| Embeddings | configurable; default to the Anthropic-recommended provider, fallback to `bge-m3` locally | multilingual required (Swedish + English) |
| Tracing | OpenTelemetry → Jaeger (dev), OTLP exporter (prod) | every span tagged with tenant, process, tier |
| Dashboard | Next.js 15, React, Tailwind, shadcn/ui, React Flow (graph and process views) | server components where possible |
| Auth | OIDC (Keycloak in compose), RBAC roles: viewer, operator, approver, admin | approvals require `approver` |
| Testing | pytest, hypothesis (fuzzing the PII boundary), Playwright (dashboard), promptfoo-style eval harness in `evals/` | |
| Packaging | Docker Compose (dev/pilot), Helm chart later | |
| Lint/format | ruff, mypy strict, prettier, eslint | pre-commit hooks |

Do not add LangChain, LlamaIndex, CrewAI, or similar frameworks. Write the agent loops directly; they must be inspectable.

---

## 4. Repository layout

```
plexus/
├── CLAUDE.md
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── specs/                        # one spec per pillar + cross-cutting specs
│   ├── 00-glossary.md
│   ├── 01-ingestion-and-graph.md
│   ├── 02-process-discovery.md
│   ├── 03-digital-twin.md
│   ├── 04-autonomy-ledger.md
│   ├── 05-actor-verifier.md
│   ├── 06-pii-boundary.md
│   ├── 07-immune-system.md
│   ├── 08-adapter-generator.md
│   ├── 09-model-router.md
│   ├── 10-dashboard.md
│   └── 11-security-and-tenancy.md
├── core/
│   ├── graph/                    # schema, store abstraction, queries
│   ├── documents/                # chunking, embeddings, pg access
│   ├── pii/                      # boundary, recognisers, token vault
│   ├── models/                   # router, providers, cost tracking
│   ├── ledger/                   # autonomy ledger, trust score
│   ├── action/                   # planner, simulator, verifier client, executor
│   ├── events/                   # unified event model, Redis streams
│   └── tenancy/                  # tenant context, RBAC
├── adapters/
│   ├── _contract/                # base classes, schemas, conformance tests
│   ├── gmail/
│   ├── clickup/
│   ├── gdrive/
│   ├── slack/                    # phase 2
│   ├── postgres_generic/         # phase 2
│   └── generator/                # pillar 8: generates new adapters
├── agents/
│   ├── extract/                  # entities + relationships from content
│   ├── discover/                 # process mining from event log
│   ├── plan/                     # actor: proposes actions
│   ├── verify/                   # verifier: independent check
│   ├── explain/                  # answers "why/what/who" with traces
│   └── immune/                   # red team + blue team
├── twin/                         # simulation engine over the graph
├── workflows/                    # Temporal workflows and activities
├── api/                          # FastAPI app, routers, auth
├── dashboard/                    # Next.js
├── evals/                        # eval sets, harness, model selection reports
├── scripts/                      # seed data, demo fixtures, migrations
└── tests/
```

---

## 5. The eight pillars (write each as a spec before building)

Each spec must contain: Purpose, Inputs, Outputs, Data model changes, Interfaces (function signatures / API routes), Failure modes, Acceptance tests, Open questions.

### Pillar 1 — Zero-schema ingestion and the knowledge graph

**Purpose.** Connect to source systems via MCP adapters and build a knowledge graph without asking the customer to define a schema up front.

**Adapter contract** (`adapters/_contract/base.py`):

```python
class PlexusAdapter(Protocol):
    id: str                         # "gmail", "clickup"
    capabilities: AdapterCapabilities   # read, write, watch, backfill
    async def backfill(self, since: datetime | None) -> AsyncIterator[SourceItem]
    async def watch(self) -> AsyncIterator[SourceEvent]     # near-real-time
    async def read(self, ref: SourceRef) -> SourceItem
    async def write(self, op: WriteOp) -> WriteResult        # ONLY callable from executor
    def describe_schema(self) -> SourceSchema               # fields, types, ids
```

`SourceItem` carries: `tenant_id`, `source_id`, `external_id`, `kind` (email, message, task, file, record), `title`, `body`, `structured: dict`, `actors: list[ActorRef]`, `timestamps`, `raw_ref`. Everything passes through the PII Boundary before leaving the adapter process.

**Seed ontology** (extend, never hard-code the customer into it):

Node labels: `Person`, `Organisation`, `Project`, `Event`, `Session`, `Concept`, `Artifact`, `Publication`, `Method`, `Question`, `Process`, `ProcessStep`, `Decision`, `Policy`, `Commitment`, `Record` (generic, with `source` and `record_type` properties).

Relationship types (initial): `WORKS_AT`, `MEMBER_OF`, `OWNS`, `PARTICIPATED_IN`, `PRODUCED`, `MENTIONS`, `DEPENDS_ON`, `FOLLOWS` (step ordering), `DECIDED_IN`, `GOVERNED_BY`, `COMMITTED_TO`, `SAME_AS` (entity resolution), `DERIVED_FROM` (provenance).

Every node and edge has: `tenant_id`, `created_at`, `valid_from`, `valid_to` (bitemporal; never overwrite, close and open), `confidence: float`, `provenance: list[SourceRef]`, `status: proposed|confirmed|rejected`.

**Extraction agent** (`agents/extract/`):
- Input: one `SourceItem` (tokenised).
- Step 1: candidate entity mentions and relations as strict JSON (schema-validated; retry once on invalid).
- Step 2: entity resolution against the graph (exact id → embedding similarity → LLM adjudication only for the top-3 ambiguous cases). Emit `SAME_AS` with confidence rather than merging destructively.
- Step 3: propose new labels/relationship types when the seed ontology does not fit; these land in an `OntologyProposal` table for human approval in the dashboard.
- Output: a `GraphDelta` (list of node/edge upserts with provenance). Deltas are applied by `core/graph/apply.py`, never by the agent directly.

**Explain agent** (`agents/explain/`): answers natural-language questions by (1) planning a Cypher + vector retrieval, (2) executing, (3) answering with inline citations to `provenance` refs. Every answer returns the subgraph used so the dashboard can render it.

**Acceptance tests.**
- Backfill 500 emails, 200 tasks, 100 files from fixtures; graph has ≥ 90% precision on a hand-labelled 100-item entity set.
- Ask "Which people were involved in project X and what did they commit to?" and get an answer citing at least three sources across two adapters.
- Zero clear-text PII in any model request log (hypothesis fuzz over the boundary).

### Pillar 2 — Process discovery from communication

**Purpose.** Mine real workflows from unstructured communication and record changes, without pre-existing event logs.

**Unified event model** (`core/events/model.py`):

```python
class PlexusEvent(BaseModel):
    tenant_id: str
    event_id: str
    ts: datetime
    actor: ActorRef            # tokenised person or system
    verb: str                  # sent, replied, created, changed_status, attached, approved, paid ...
    objects: list[ObjectRef]   # object-centric: an event touches several objects
    source: SourceRef
    attributes: dict           # from_status, to_status, amount, etc.
```

- Every adapter emits `PlexusEvent`s for structured changes directly (status change in ClickUp, file created in Drive).
- For unstructured content (email, chat), the **event synthesiser** agent turns a thread into events: "Anna asked for a quote", "Erik sent quote v2", "customer accepted". Use a fixed verb vocabulary (`core/events/verbs.py`); the model may propose new verbs only via `OntologyProposal`.
- Events land in a Postgres `event_log` table (object-centric event log format, compatible in spirit with OCEL 2.0 so it can be exported).

**Discovery agent** (`agents/discover/`):
- Groups events by shared object ids into cases.
- Runs a deterministic miner first (implement a simple directly-follows graph + heuristic miner in pure Python; do not pull in heavy process-mining libs unless a spec justifies it).
- Uses the model only to (a) name the discovered process, (b) label steps in plain language, (c) detect variants that are actually the same step phrased differently.
- Writes `Process` and `ProcessStep` nodes with `FOLLOWS` edges, plus metrics: median cycle time, step frequency, common bottleneck, actors per step, variant count.
- Every discovered process starts at tier **Observe** in the Autonomy Ledger.

**Acceptance tests.**
- From seeded fixtures containing a "customer enquiry → quote → acceptance → invoice" flow spread across Gmail and ClickUp, the miner discovers a 4 to 6 step process with correct ordering and a cycle time within 10% of the ground truth.
- A human can merge two variants in the dashboard; the merge is stored as a correction and the miner respects it on re-run.

### Pillar 3 — Digital twin and shadow mode

**Purpose.** Simulate a proposed action against the graph before it is taken and show the predicted consequences.

- `twin/engine.py` takes a `ProposedAction` and a graph snapshot, applies the action to a copy (never the live graph), and returns a `SimulationReport`: nodes/edges that would change, policies that would be violated (`GOVERNED_BY` edges with rule expressions evaluated by a small safe rule engine, not `eval`), downstream commitments affected, and a plain-language summary generated by the workhorse model **from the structured diff only** (the model never invents effects that are not in the diff).
- **Shadow mode**: a process at Observe/Explain tier still runs the full plan → simulate pipeline on real events and records what it *would* have done. These shadow runs feed the trust score before any real action is ever taken.
- Policy rules are stored as structured JSON (field, operator, value, scope) authored in the dashboard; an initial library covers spending limits, approval requirements, data-residency, and working-hours constraints.

**Acceptance tests.**
- A proposed "approve invoice" action against a policy "amount > 10 000 SEK requires approver" is flagged with the correct rule id.
- Shadow runs on 50 seeded events produce a report each, with zero writes to any adapter (assert via executor call count = 0).

### Pillar 4 — The Autonomy Ledger

**Purpose.** Make autonomy earned, measurable, auditable, and reversible per process.

**Tiers:** `OBSERVE` → `EXPLAIN` → `SUGGEST` → `ACT_WITH_APPROVAL` → `AUTONOMOUS`.

**Ledger** (`core/ledger/`): append-only Postgres table `ledger_entries` with `tenant_id`, `process_id`, `entry_type` (shadow_run, suggestion, approval, rejection, execution, reversal, promotion, demotion, manual_override), `actor`, `payload`, `trace_id`, `ts`, and a hash chain (`prev_hash`, `hash`) so tampering is detectable.

**Trust score** (start with this; parameters live in config, changes require sign-off):

```
trust = w1 * approval_rate(last N)      # approvals / (approvals + rejections)
      + w2 * (1 - reversal_rate(last N))
      + w3 * recency_factor(days_since_last_error)
      - w4 * blast_radius_penalty(process)
N = 30, weights default 0.4 / 0.3 / 0.2 / 0.1
blast_radius = f(records_touched, money_touched, external_parties_touched), normalised 0..1
```

**Promotion rules:** promote one tier when `trust ≥ threshold[tier]` AND minimum sample size met AND no reversal in the last 14 days AND an `approver` confirms (promotion is never silent). **Demotion:** any reversal drops one tier immediately and automatically; any policy violation in an executed action drops to `OBSERVE`. Every promotion/demotion is a ledger entry.

**Kill switch:** a tenant-level and process-level `paused` flag checked by the executor on every action; the API exposes it and the dashboard shows a big red control.

**Acceptance tests.**
- Simulate 40 approvals and 1 reversal; score and tier follow the formula exactly (property-based tests).
- Hash chain validation detects a tampered row.
- Executor refuses to execute when paused, with a ledger entry recording the refusal.

### Pillar 5 — Actor / Verifier separation of duties

**Purpose.** No single model gets to both propose and approve an action.

**Actor** (`agents/plan/`): given a triggering event + process + graph context, produces a `ProposedAction`: target adapter, operation, arguments, rationale, cited context (graph refs), expected effects, and a self-declared risk class.

**Verifier** (`agents/verify/`): a **different vendor** from the actor. Receives the `ProposedAction`, the `SimulationReport`, applicable policies, and the recent ledger for that process. Returns a `Verdict`: `approve | reject | escalate`, with reasons mapped to policy ids or graph facts. The verifier prompt is adversarial by design ("assume the proposal is wrong; find why"). The verifier cannot modify the proposal, only judge it.

**Execution rules:**
- `SUGGEST` tier: proposal + verdict shown to a human; nothing executes.
- `ACT_WITH_APPROVAL`: verdict must be `approve` AND a human approver clicks approve.
- `AUTONOMOUS`: verdict must be `approve`; executes; human gets a post-hoc notification with a one-click reversal where the adapter supports it.
- `escalate` always routes to a human regardless of tier.

**Acceptance tests.**
- Router refuses to boot in `env=production` if `actor.vendor == verifier.vendor`.
- A proposal that violates a policy is rejected by the verifier in ≥ 95% of 100 seeded adversarial cases.
- No execution occurs without a stored verdict (DB constraint + test).

### Pillar 6 — PII Boundary

**Purpose.** Models never see clear-text personal data; customer systems never receive tokens.

- `core/pii/boundary.py`: `tokenize(text|dict) -> (tokenised, TokenMap)`, `restore(tokenised, TokenMap) -> original`.
- Presidio analyzer with custom recognisers: Swedish personnummer/samordningsnummer, Swedish org-nr, phone (+46 formats), IBAN/Bankgiro/Plusgiro, Swedish street addresses, names (sv + en NLP models).
- Tokens are format-preserving and stable per tenant (`<PERSON_7f3a>`), so the graph can still resolve "the same person" across sources without storing the real value in the graph. The **token vault** (Postgres, encrypted at rest with a per-tenant key from the KMS abstraction; local dev uses a file-based key) is the only place real values live.
- Restore happens exclusively inside `core/action/executor.py`, immediately before the adapter write, and the restored payload is never logged.
- GDPR deletion: `DELETE /v1/tenants/{t}/subjects/{token}` erases the vault entry and marks graph nodes as `erased`; embeddings referencing the subject are re-computed from tokenised text (which they already are, so nothing to do) and documents are purged.

**Acceptance tests.**
- Hypothesis fuzz: generate 10 000 Swedish/English strings with embedded PII; boundary catches ≥ 99% of seeded PII, and restore is lossless.
- Grep of all model request logs in a full end-to-end demo run finds zero matches for seeded real values.

### Pillar 7 — Immune system

**Purpose.** Continuously red-team every adapter input surface and harden against prompt injection.

- `agents/immune/red.py`: generates injection payloads (direct, indirect via document content, multilingual, encoding tricks, tool-call hijack attempts) and injects them into a **sandbox tenant** that mirrors the real adapters with fixture data.
- `agents/immune/blue.py`: detects successful attacks (a model call that produced an unexpected tool call, a policy bypass, leaked tokens), proposes a mitigation (input filter rule, prompt hardening, allow-list change), and opens a `MitigationProposal` for human review. Approved mitigations are applied as versioned config, not code edits.
- Runs on a schedule (nightly) and on every adapter change. Results appear as a live "immune score" on the dashboard with trend.
- Red-team payloads and outcomes are stored so the eval set grows over time.

**Acceptance tests.**
- On a fresh install, the red agent finds at least one working injection in a deliberately weak fixture adapter; after the blue agent's mitigation is applied, the same payload fails.
- Immune runs never touch a non-sandbox tenant (assert by tenant id on every span).

### Pillar 8 — Self-extending adapter generator

**Purpose.** For a system with no adapter, generate one from its API spec or DB schema, test it in a sandbox, and hand it to a human.

- Input: an OpenAPI/GraphQL spec URL, a Postgres/MySQL connection string (read-only), or a short description plus example payloads.
- The generator (a coding-agent loop using the actor model) produces a full MCP server implementing `PlexusAdapter`, plus conformance tests from `adapters/_contract/conformance/`.
- It runs the conformance suite in an isolated container against read-only data. Write capabilities are generated **disabled** and can only be enabled by an `admin` after review.
- Output is a PR-like review object in the dashboard: generated code diff, test results, detected schema, proposed event mappings.

**Acceptance tests.**
- Given a small OpenAPI spec for a fictional invoicing tool (fixture), the generator produces an adapter that passes backfill/read conformance tests without human edits in ≥ 3 of 5 runs.
- Generated adapters cannot import `executor` or expose `write` as enabled by default (static check in CI).

---

## 6. Model router

`core/models/router.py` exposes: `complete(role, messages, tools=None, schema=None)`, where `role ∈ {actor, verifier, workhorse, classifier, embedder}`. Config (`config/models.yaml`):

```yaml
roles:
  actor:      { vendor: anthropic, model: claude-fable-5-1, effort: high }
  workhorse:  { vendor: anthropic, model: claude-sonnet-5 }
  classifier: { vendor: anthropic, model: claude-haiku-4-5 }
  verifier:   { vendor: openai,    model: gpt-5.5 }        # MUST differ from actor vendor
  embedder:   { vendor: local,     model: bge-m3 }
profiles:
  sovereign:                                                # for customers that cannot send data out
    actor:     { vendor: local, model: qwen3.6-plus }
    verifier:  { vendor: local, model: deepseek-v4 }
    workhorse: { vendor: local, model: glm-5.3 }
```

Requirements: structured output enforced by JSON schema and validated by Pydantic; automatic single retry on invalid JSON; per-tenant cost accounting (tokens × price) written to Postgres; timeouts and circuit breaker per vendor; prompt caching where the vendor supports it; all prompts live in `prompts/*.md` with a version header, never inline in Python.

Verify model names against the vendor's current model list at build time and update the config if any are deprecated. Write `evals/model_selection.md` after Phase 1 with results from the eval harness; the harness decides model assignments, not this table.

---

## 7. Cross-cutting requirements

**Tenancy.** Every table, node, edge, stream key, and span carries `tenant_id`. Row-level security in Postgres; graph queries always include a tenant predicate (enforced by the store abstraction; raw Cypher from agents is rejected if it lacks it).

**Security.** OIDC; RBAC (viewer, operator, approver, admin); secrets via env + Docker secrets; adapters run as separate processes with least-privilege credentials; outbound network allow-list per adapter; dependency scanning in CI.

**Observability.** Structured JSON logs; OpenTelemetry spans for every model/tool/graph/action call; Jaeger in compose; `/v1/health` deep checks per dependency; per-tenant cost dashboard.

**GDPR / EU AI Act readiness.** Data map generated from adapter schemas; records of processing exported as JSON; ledger + traces satisfy logging obligations for high-risk-adjacent use; human oversight is structural (tiers). Data residency: all storage in compose is local; document in `docs/compliance.md`.

**Internationalisation.** Swedish and English throughout: extraction prompts, event synthesis, dashboard strings (i18n from day one, `sv` and `en`).

**Performance targets (pilot scale).** 100k source items, 1M events, 500k graph nodes; Explain query p95 < 4s; ingestion throughput ≥ 20 items/s on a laptop.

---

## 8. Dashboard (Next.js)

Pages: **Overview** (tenant health, immune score, cost, tier distribution), **Graph** (React Flow explorer with provenance drawer), **Processes** (discovered processes as swimlane/DFG views, metrics, variant merge, tier badge, promote/pause controls), **Inbox** (suggestions and approvals with the proposal, simulation report, verdict, one-click approve/reject/reverse), **Ledger** (filterable, exportable, hash-chain status), **Adapters** (connected systems, generator wizard, review queue for generated adapters), **Ontology** (proposals awaiting approval), **Policies** (rule editor), **Immune** (runs, findings, mitigations), **Ask** (Explain agent chat with cited subgraph).

Design: calm, dense, professional; no marketing gradients. Accessibility AA. Mobile-usable for the Inbox page (approvers will use phones).

---

## 9. Build phases and Definition of Done

**Phase 0 — Skeleton (days 1–2).** Repo layout, compose stack boots, CI runs lint/type/tests, `CLAUDE.md`, all 12 spec files drafted (can contain open questions). DoD: `make up && make test` green on a clean machine.

**Phase 1 — Ingest + Graph + Explain (weeks 1–3).** Pillars 1 and 6; adapters gmail, clickup, gdrive; router with cost tracking; eval harness v1; Overview, Graph, Ask, Adapters pages. DoD: Pillar 1 and 6 acceptance tests pass; demo script `scripts/demo_phase1.sh` seeds fixtures and answers three cross-system questions with citations.

**Phase 2 — Events + Process discovery + Twin (weeks 4–6).** Pillars 2 and 3; Processes and Policies pages; shadow mode running on every discovered process. DoD: Pillar 2 and 3 tests pass; demo shows a discovered process with cycle time and a shadow-run report.

**Phase 3 — Ledger + Actor/Verifier + Inbox (weeks 7–9).** Pillars 4 and 5; Inbox and Ledger pages; first real write (ClickUp task status change) at ACT_WITH_APPROVAL. DoD: Pillar 4 and 5 tests pass; a full approve → execute → reverse cycle is visible in the ledger with a valid hash chain.

**Phase 4 — Immune + Generator + Pilot hardening (weeks 10–12).** Pillars 7 and 8; Immune and Ontology pages; Slack + generic Postgres adapters; sovereign model profile tested with Ollama; compliance docs; load test at pilot scale. DoD: all pillar tests pass; `docs/pilot-runbook.md` lets a new engineer install Plexus at a customer in under one day.

Do not reorder phases. Do not build Pillar 8 before Pillar 1 exists.

---

## 10. Working method (how you, Claude Code, should operate)

1. **Plan first, every session.** Start by reading `CLAUDE.md`, the relevant `specs/` file, and `docs/STATUS.md`. State the plan for the session in ≤ 10 bullets. Then execute.
2. **Spec-driven.** If the spec is missing or ambiguous, write or amend the spec, list the open questions in `docs/QUESTIONS.md` addressed to me, and proceed with the most conservative interpretation.
3. **Tests with every change.** Acceptance tests derived from the spec, unit tests for logic, property-based tests for the ledger and PII boundary. No PR without tests.
4. **Small, reviewable commits.** Conventional commits (`feat(ledger): ...`). One pillar per branch. Update `docs/STATUS.md` at the end of every session with what is done, what is next, and any decisions made.
5. **Never mock the safety path.** You may mock external vendors in tests, but the executor, verifier gate, PII boundary, and pause flag must be exercised for real in integration tests.
6. **Ask before**: adding paid dependencies, changing the graph schema post-Phase 1, changing the trust formula, enabling any write capability, or touching production config.
7. **Prefer boring.** Plain Python, explicit data classes, readable Cypher. No clever metaprogramming. Optimise only with a benchmark in hand.
8. **Document as you go.** `docs/architecture.md` (with Mermaid diagrams), `docs/adr/` for every significant decision (ADR format), `docs/compliance.md`, `docs/pilot-runbook.md`.
9. **Language.** Code and docs in English. All user-facing strings go through i18n with `sv` and `en`.
10. **Report honestly.** If something in this brief is wrong, infeasible, or a worse idea than an alternative, say so in `docs/QUESTIONS.md` with your reasoning and your recommendation. Do not silently deviate.

---

## 11. Seed fixtures and demo scenario

Create `scripts/fixtures/` with a fictional company **Nordvik Konsult AB** (12 people, Swedish + English communication): 500 emails, 200 ClickUp tasks across 3 lists, 100 Drive files, 6 months of activity, containing three ground-truth processes (customer enquiry → quote → acceptance → invoice; new-hire onboarding; monthly reporting), ~40 seeded PII values of each recogniser type, and 20 planted prompt-injection payloads in documents. Ground-truth labels live in `scripts/fixtures/labels/`. All acceptance tests and demos run against this dataset. Never use real customer data in fixtures.

---

## 12. Definition of "extremely useful" for customer zero (TCL)

The pilot succeeds if, within a week of install at TCL, Plexus can:
1. Answer "who has worked with organisation X, in which sprints, and what came out of it" with citations.
2. Show the real cycle time of the sprint-to-publication process and where it stalls.
3. Draft follow-up emails after network events at SUGGEST tier with a verifier verdict attached.
4. Reach ACT_WITH_APPROVAL on one low-risk process (e.g., creating ClickUp tasks from meeting notes) with a clean ledger.

Design every early decision toward those four outcomes.

---

## CLAUDE.md contents (copy into ./CLAUDE.md)

```markdown
# Plexus — engineering rules

You are building Plexus, an organisational nervous system. Read specs/ before coding.

## Hard rules
- Only core/action/executor.py may call adapter write methods.
- All model calls go through core/models/router.py. No vendor SDK imports elsewhere.
- Actor and verifier vendors must differ in production; router refuses to boot otherwise.
- Every byte leaving an adapter passes core/pii/boundary.py. Restore only in executor.
- Every graph node/edge and every table row has tenant_id. Store abstraction enforces it.
- Ledger is append-only with a hash chain. Never update or delete ledger rows.
- Long-running or waiting work runs in Temporal workflows. No bare loops.
- No LangChain/LlamaIndex/CrewAI. Agent loops are explicit Python.
- Prompts live in prompts/*.md with a version header, never inline.
- Specs before code; tests with every change; update docs/STATUS.md every session.

## Stack
Python 3.12 + FastAPI + Temporal + Neo4j + Postgres/pgvector + Redis + Presidio + MCP;
Next.js 15 dashboard; OpenTelemetry; Docker Compose. uv + pnpm. ruff, mypy strict.

## Commands
make up / make down / make test / make lint / make demo / make evals

## Ask before
Paid dependencies, graph schema changes after Phase 1, trust formula changes,
enabling any adapter write capability, production config.

## When unsure
Choose the simplest, most auditable, most reversible option and log the question
in docs/QUESTIONS.md.
```

---

*Begin with Phase 0. Confirm the plan for the session, then start.*
