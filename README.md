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

## Deploying

See [DEPLOY.md](DEPLOY.md). Both the console and the service run on Vercel, backed by a managed
Postgres — every screen is answered from Postgres and the event log. A host that runs containers
gives the full stack, with the graph store and a Temporal worker. The engineering rules are in
[ENGINEERING.md](ENGINEERING.md).
