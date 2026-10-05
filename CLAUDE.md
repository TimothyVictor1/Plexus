# Plexus

An intelligence layer that plugs into the tools a company already uses, works out how work
actually moves through that company, and earns the right to act inside those tools one process
at a time.

**Read this first, then `ENGINEERING.md` (the rules), `docs/STATUS.md` (where things stand) and
the spec in `specs/` for whatever you are changing.** The rules in `ENGINEERING.md` are rules,
not preferences; violating one is a bug.

---

## What it does

Six screens, and the product is the honesty of each one.

| Screen | Route | What it is |
|---|---|---|
| Home | `/{locale}` | What needs you, and what is worth knowing |
| Ask | `/{locale}/ask` | Questions about the company, answered from its own records, with sources |
| Your work | `/{locale}/work` | The processes Plexus found by itself, worst first |
| What if | `/{locale}/twin` | A live model of how work moves; ask what happens if someone leaves |
| To review | `/{locale}/review` | What Plexus has prepared and is waiting on a person to approve |
| Connections | `/{locale}/connections` | The tools it reads from, and exactly what each would see |

Plus the marketing landing page at `/` and the confidentiality gate at `/gate`.

### The thesis, which everything else serves

**Autonomy is earned.** A process starts at OBSERVE and climbs a ladder — OBSERVE, EXPLAIN,
SUGGEST, ACT_WITH_APPROVAL, AUTONOMOUS — only when its track record justifies it. A freshly
seeded organisation therefore has an **empty "To review" screen** and refuses promotion with
"0 decisions, needs 10". That is the product working, not a fault. Do not "fix" it.

---

## How it is built

```
core/        the graph, documents, the PII boundary, the model router, the ledger,
             the action pipeline, events, tenancy, ask, insights, language, org,
             processes, review, team
adapters/    connectors. every tool speaks one protocol
agents/      explicit Python loops: extraction, discovery, planning, verification, triggers
twin/        the digital twin, the simulator and the policy engine
workflows/   background jobs. tasks.py holds the jobs; jobs.py is the Temporal half
api/         FastAPI, everything under /v1 (14 routers)
dashboard/   the console. Next.js 15, React 19, Swedish and English
specs/       one spec per pillar (00-11). code is written from these
docs/        STATUS.md, QUESTIONS.md, product-brief.md, architecture.md, compliance.md, adr/
```

**271 tests across 23 files.** Integration tests need `PLEXUS_INTEGRATION=1` and the stack up.

### The parts that matter

- **Object-centric event log.** Cases are built by union-find over shared object ids; a
  directly-follows graph plus a heuristic dependency measure discovers processes. Nothing about
  the processes is configured — they are mined.
- **PII boundary** (`core/pii/`). Every byte leaving an adapter is tokenised before it reaches a
  model. Tokens are HMAC-derived and stable per tenant. Only `core/action/executor.py` restores.
- **The ledger** (`core/ledger/`). Append-only, SHA-256 hash-chained, with a database trigger
  that rejects UPDATE and DELETE. Trust is computed from it and gated on a minimum number of
  decisions.
- **The model router** (`core/models/router.py`). Every model call goes through it. Roles are
  spread across models because the free tier quotas are per-model (`config/models.yaml`).

---

## Running it

```bash
make up        # the Compose stack
make seed      # the demo organisation
make worker    # background jobs, another terminal
make console   # the console on :3000
make doctor    # checks all four and says what to fix
make test      # unit + architecture + property tests
make lint      # ruff, ruff format, mypy strict, compose validation
```

The console alone, against the hosted service:

```bash
cd dashboard && pnpm install && pnpm dev
```

---

## Where it is deployed

Everything runs on **Railway**, in `europe-west4` (Amsterdam), against **Neon Postgres** in
Frankfurt. Both services live in the Railway project `plexus`.

| | URL |
|---|---|
| Console | https://plexus-console-production.up.railway.app |
| Service | https://plexus-service-production.up.railway.app |
| API docs | `…/v1/docs` |

The console is behind a confidentiality gate: a notice plus one shared password, checked in
middleware. Set `PLEXUS_ACCESS_PASSWORD` to enable it; unset means no gate, which is what local
development wants.

Vercel is **not** used any more. Those projects were deleted; if a `vercel.json` ever reappears
at the repository root it will be applied to every service in a project and break the console's
build. `vercel.service.json` is kept as a record only.

### Environment

Service: `DATABASE_URL`, `PLEXUS_KMS_KEY`, `CRON_SECRET`, `GOOGLE_API_KEY`, `GRAPH_ENABLED=false`,
`JOBS_SCHEDULER=cron`, `POSTGRES_POOL_MAX=3`, empty `REDIS_URL` / `PRESIDIO_*`,
`PLEXUS_CONSOLE_ORIGINS` = the console's URL.

Console: `NEXT_PUBLIC_PLEXUS_API`, `PLEXUS_ACCESS_PASSWORD`, `PLEXUS_GATE_SECRET`.

`PLEXUS_KMS_KEY` **must be identical between seeding and serving.** That one key derives every
PII token and encrypts the vault. Seed with one key and serve with another and nothing matches
what is stored — quietly, with no error.

### What a container host does not give it

Three things, each configuration rather than a second code path, all documented in `DEPLOY.md`:
no graph store (`GRAPH_ENABLED=false`), no Temporal worker (`JOBS_SCHEDULER=cron`, and
`/v1/jobs/maintenance` on a schedule), and no Presidio or Redis — nothing calls either today.

---

## The look

One language across the landing page and the console.

| | |
|---|---|
| Ground | `#000000` |
| Type | Inter |
| Headings | `BubbledotICG-FinePos`, a dot-matrix face, from OnlineWebFonts |
| Primary control | White pill with a soft glow |
| Accent | Lavender `--hi` (`#A78BFA` dark, `#6D28D9` light) |
| Motion | Motion (`motion/react`), easing `[0.22, 1, 0.36, 1]` everywhere |

**The accent is rationed.** It means "look here" and nothing else: where you are in the rail,
what has focus, what is waiting, how far a process has been trusted, and links. Surfaces, cards
and type stay monochrome. Do not spend it on decoration.

**Health reads as brightness, not hue**, because there is no hue to spend. What needs a person
is the brightest thing in the dark theme and the darkest in the light one. Both themes are
measured: nothing below 4.5:1.

Light mode is a choice, not inherited from the operating system — dark is what Plexus is. The
stored theme is applied by an inline script before first paint; a stylesheet would arrive too
late and a light-theme visitor would see a black flash on every load.

The landing page lives in its own route group with its own `<html>` and shares none of the
console's chrome. Its two assets — `dashboard/public/landing/logo.webp` and the local fallback
font — are optional and documented in that directory's README.

---

## Things that have already bitten, so they do not have to again

- **A stylesheet that stands alone needs its own box model.** `landing.css` does not get the
  console's reset, so page padding was added to `height:100dvh` and the footer fell below the
  fold. Measure the rendered page; do not read the CSS and assume.
- **An `<img>` that 404s during the server render has already failed by hydration**, so React's
  `onError` never fires and the broken-image icon stays. Probe the file instead.
- **Redeploying a deployment reuses *that deployment's* config**, not the service's current
  settings. After changing a service setting, trigger a fresh deploy.
- **A health check must not point at a route the gate protects.** `/en` returns 307 once the
  gate is on, the host reads that as unhealthy, and the deploy is killed. It points at `/gate`.
- **Free-tier model quotas are per model and per day.** Six names requested in quick succession
  during seeding will fall back to the rule engine. That is the fallback working; re-run
  `refresh_labels` later and they come back model-written.
- **Co-locate the service with the database.** Running in San Francisco against Frankfurt made
  the home page take 51 seconds. In Amsterdam it takes 4.
- **A pooled Postgres needs prepared statements off.** `core/db/pool.py` detects a pooler and
  does it; without that, every other query fails.

---

## Ask before

Paid dependencies, graph schema changes, trust formula changes, enabling any adapter write
capability, production config. When unsure, pick the simplest, most auditable, most reversible
option and log the question in `docs/QUESTIONS.md`.

## Every session

Update `docs/STATUS.md`. Tests with every change. `make lint` and `make test` before you claim
anything works — and for anything that renders, look at it, or measure it.
