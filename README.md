# Plexus

An intelligence layer that plugs into the tools a company already uses, learns how that company
actually works, and earns the right to act inside those tools one process at a time.

It connects through MCP connectors, builds a map of the work from real email, tickets, files and
records, simulates an action before taking it, and promotes each way of working up an autonomy
ladder only when its track record justifies it.

**Autonomy is earned, not switched on.** Every write goes through one pipeline. Every action is
judged independently before it runs. Every personal detail is replaced before a model sees it.
Every decision lands in an append-only, hash-chained record.

Built for EU hosting, GDPR and the EU AI Act.

---

## What it does

| Screen | What it is for |
|---|---|
| **Home** | What needs you, and what is worth knowing, in one glance |
| **Ask** | Questions about your own company, answered from your own tools, with sources |
| **Your work** | The ways work gets done here, found automatically, worst first |
| **What if** | A live model of how work moves. Ask what happens if someone leaves, if more work arrives, or if a process changes |
| **To review** | What Plexus has prepared and is waiting on you to approve |
| **Connections** | The tools it reads from, and exactly what each one would see |

## Running it

Requirements: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22, pnpm.

```bash
cp .env.example .env
make up          # Postgres, Neo4j, Redis, Temporal, Jaeger, Keycloak, Presidio, the service
make seed        # a demo organisation with six processes and work in flight
make worker      # background jobs, in another terminal
make console     # the console on http://localhost:3000
```

`make doctor` checks all four and tells you what to fix if something is wrong.

| Service | Address |
|---|---|
| Console | http://localhost:3000 |
| API docs | http://localhost:8000/v1/docs |
| Temporal | http://localhost:8233 |
| Neo4j | http://localhost:7474 |
| Traces | http://localhost:16686 |

Set `GOOGLE_API_KEY` in `.env` for plain-language names and drafted messages. Without it
everything still works, using built-in rules instead of a model.

A real organisation starts empty:

```bash
uv run python -m scripts.seed --org yourco --name "Your Company"
```

## Deploying

See [DEPLOY.md](DEPLOY.md). The console runs on Vercel from `dashboard/`; the service needs
somewhere that runs containers.

## How it is built

| Path | What lives there |
|---|---|
| `core/` | The graph, documents, the PII boundary, the model router, the ledger, the action pipeline, events, tenancy |
| `adapters/` | Connectors. Every tool speaks one protocol |
| `agents/` | Explicit Python loops: extraction, discovery, planning, verification, triggers |
| `twin/` | The digital twin, the simulator and the policy engine |
| `workflows/` | Background jobs, on a Temporal schedule |
| `api/` | The service, versioned under `/v1` |
| `dashboard/` | The console. Next.js, Swedish and English |
| `specs/` | One spec per pillar. Code is written from these |

## The rules

[ENGINEERING.md](ENGINEERING.md) holds the non-negotiables: a single write path, the PII
boundary, separation between proposing and approving, tenancy everywhere, an append-only
ledger, and no agent frameworks. Where they can be enforced by the build rather than by
review, they are: `tests/architecture/` parses every file and fails on a violation.

```bash
make test    # unit, property-based and architecture tests
make lint    # ruff, mypy strict, compose validation, console checks
PLEXUS_INTEGRATION=1 uv run pytest -m integration   # against the running stack
```
