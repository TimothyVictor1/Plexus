# Plexus

An organisational nervous system: a system-agnostic intelligence layer that plugs into a
company's existing tools (email, chat, CRM, tickets, drives, databases) through MCP adapters,
builds a living knowledge graph and process graph, simulates actions before taking them, and
promotes each process up an autonomy ladder only when its track record justifies it.

**Autonomy is earned, not switched on.** Every write to a customer system goes through one
pipeline (plan → simulate → verify → approve/auto → execute → record), every action is judged by
a second model from a different vendor, every PII value is tokenised before a model sees it, and
every decision lands in an append-only, hash-chained ledger.

Customer zero: Tech Concept Lab, Karlskrona. Designed for EU hosting, GDPR, and the EU AI Act.

## Status

Phase 0 (skeleton). See [docs/STATUS.md](docs/STATUS.md) for what is done and what is next, and
[docs/QUESTIONS.md](docs/QUESTIONS.md) for open decisions.

## Quick start

Requirements: Docker Desktop (running), Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22, pnpm.

If `corepack enable` fails with a permissions error on `/usr/local/bin` (common on macOS), install
pnpm without sudo instead:

```bash
npm install -g pnpm@9 --prefix ~/.local
```

and make sure `~/.local/bin` is on your `PATH`. Until then `npx pnpm@9 --dir dashboard run <script>` works.

First `make up` pulls roughly 6–8 GB of images (Neo4j, Keycloak, Temporal, Presidio); allow
10–20 minutes on a laptop. Subsequent boots take under a minute.

```bash
cp .env.example .env
make up      # boots Postgres/pgvector, Neo4j, Redis, Temporal, Jaeger, Keycloak, Presidio, API
make test    # unit + architecture tests
make lint    # ruff, mypy strict, compose validation
```

Local endpoints once `make up` is green:

| Service | URL |
|---|---|
| Plexus API | http://localhost:8000/v1/health |
| Temporal UI | http://localhost:8233 |
| Neo4j Browser | http://localhost:7474 |
| Jaeger | http://localhost:16686 |
| Keycloak | http://localhost:8080 |

## Repository map

| Path | What lives there |
|---|---|
| `specs/` | One spec per pillar plus cross-cutting specs. Code is implemented from these, not from memory. |
| `core/` | Graph store, documents, PII boundary, model router, ledger, action pipeline, events, tenancy |
| `adapters/` | MCP adapters (`_contract/` holds the base classes and conformance tests) |
| `agents/` | Explicit Python agent loops: extract, discover, plan (actor), verify, explain, immune |
| `twin/` | Simulation engine (digital twin, shadow mode) |
| `workflows/` | Temporal workflows and activities |
| `api/` | FastAPI app, versioned under `/v1` |
| `dashboard/` | Next.js 15 dashboard (sv + en) |
| `evals/` | Eval sets, harness, model-selection reports |
| `scripts/` | Seed data (Nordvik Konsult AB fixtures), demos, migrations |
| `docs/` | Architecture, ADRs, status, questions, compliance, pilot runbook |
| `prompts/` | Versioned prompt files; never inline in Python |

## Engineering rules

Read [ENGINEERING.md](ENGINEERING.md). The non-negotiable principles (single write path, PII boundary,
two-vendor separation, full tracing, append-only ledger, tenancy everywhere, Temporal for anything
that waits, no agent frameworks) are enforced structurally where possible; see
`tests/architecture/`.
