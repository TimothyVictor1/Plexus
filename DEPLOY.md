# Deploying Plexus

Plexus is two pieces:

- **the console** — Next.js, in `dashboard/`. A thin client. It holds no data.
- **the service** — FastAPI, in `api/` and `core/`. Everything real happens here.

Both can run on Vercel, and the whole product works there: what needs you, the ways work gets
done, the what-if model, questions answered from your own records with sources, the review queue
and the connections. That is because every one of those screens is answered from **Postgres and
the event log**. The rest of the local stack is real but optional, and what each missing piece
costs is written down below rather than hidden.

The full Compose stack is still the reference deployment. Vercel is the quickest way to get a
working link.

---

## The short version

Two Vercel projects from this one repository, plus a managed Postgres.

| Project | Root Directory | What it is |
|---|---|---|
| `plexus-console` | `dashboard` | the console |
| `plexus-service` | `.` (repository root) | the service |

Then seed the database once from your own machine, and point the console at the service.

---

## 1. A database

Any Postgres reachable from the internet: Vercel Postgres, Neon, Supabase, RDS. Choose an EU
region if data residency matters to you — Plexus is built for it, but the region is your choice,
not something it can claim on your behalf.

Copy the connection string. If the host offers a **pooled** one, take that: a serverless function
is many short-lived copies sharing one database, and a pooler is what keeps them from exhausting
it. Plexus detects a pooled string and turns off prepared statements accordingly.

## 2. The service

Import the repository at [vercel.com/new](https://vercel.com/new) and leave **Root Directory** at
the repository root. `vercel.json` and `[tool.vercel]` in `pyproject.toml` do the rest: the whole
FastAPI app is deployed as one function from `service.py`.

Set these environment variables:

| Variable | Value |
|---|---|
| `DATABASE_URL` | the connection string from step 1 |
| `GRAPH_ENABLED` | `false` |
| `JOBS_SCHEDULER` | `cron` |
| `CRON_SECRET` | any long random string |
| `POSTGRES_POOL_MAX` | `3` |
| `REDIS_URL` | *(empty)* |
| `PRESIDIO_ANALYZER_URL` | *(empty)* |
| `PRESIDIO_ANONYMIZER_URL` | *(empty)* |
| `PLEXUS_KMS_KEY` | 64 hex characters. Generate with `python -c "import secrets;print(secrets.token_hex(32))"` |
| `GOOGLE_API_KEY` | your Gemini key. Without it everything still works, using built-in rules |
| `PLEXUS_CONSOLE_ORIGINS` | the console's URL, once you have it from step 4 |

The empty ones are not a formality. An empty address means "this deployment does not have one",
and `/v1/health` then reports only what is actually there — otherwise a Vercel deployment would
report itself down forever and look broken.

## 3. Fill the database

Once, from your own machine, pointed at the hosted database:

```bash
export DATABASE_URL='...'          # the same string, in quotes
export PLEXUS_KMS_KEY='...'        # the same key as the service. This matters — see below
export GRAPH_ENABLED=false
uv run python -m core.db.migrate
uv run python -m scripts.seed                      # an example organisation
# or: uv run python -m scripts.seed --org yourco --name "Your Co"
```

`migrate` creates the schema and the row-level security policies. `seed` ingests, mines the
processes out of the event log and names them. It prints what it found.

**`PLEXUS_KMS_KEY` must be the same value here and in the service.** That one key decides both
how personal details are tokenised and how the vault that holds them is encrypted. Seed with one
key and serve with another and the tokens will not match what is stored. Locally this is a file
under `config/`, created on first use; a serverless host has no disk to keep it on, so there it
has to come from the environment.

### What you will see, and what you will not

A newly seeded organisation has an **empty "To review"** screen, and the autonomy control on each
process refuses to move with something like *"0 decisions, needs 10"*. That is the product
working, not a fault: Plexus starts out only watching, and earns the right to prepare anything
from a track record it does not have yet. The other five screens are full immediately — the ways
work gets done, the slow steps, the what-if model, the questions and the connections.

## 4. The console

Import the same repository again as a second project, and **set Root Directory to `dashboard`**.
Nothing builds without that.

Set one environment variable:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_PLEXUS_API` | the service URL from step 2 |

Then go back to the service project, set `PLEXUS_CONSOLE_ORIGINS` to this console's URL, and
redeploy it. That is the CORS allowance; the browser will not call the service without it.

---

## What Vercel does not give it

Three things, each one configuration rather than a second code path.

**No graph store.** The knowledge graph is a second database on top of Postgres. Only the map on
Settings › Advanced reads it, and with `GRAPH_ENABLED=false` that panel says there is none
instead of failing. Ingestion skips the graph deltas and still writes every document, token and
event — which is what every other screen reads.

**No Temporal worker.** Temporal is how the routine jobs are normally scheduled and retried, and
it stays the default wherever a worker can stay alive. A serverless host cannot keep one, so
`JOBS_SCHEDULER=cron` calls the same functions over HTTP instead. They live in
`workflows/tasks.py`; the Temporal activities in `workflows/jobs.py` are thin wrappers around
them, so there is one definition of each job either way. `vercel.json` schedules
`/v1/jobs/maintenance` every six hours, and `CRON_SECRET` is what that trigger presents. With no
secret set the endpoint refuses outright, so an unconfigured deployment cannot be driven by
someone who happens to know the path.

**No Presidio, no Redis.** Nothing in the code calls either one today. Personal details are
tokenised by `core/pii/boundary.py` before anything leaves an adapter, exactly as they are
locally.

The console says which scheduler is in use rather than implying a durable worker that is not
there. If you later move the service to a host that runs containers, unset these variables and
the full stack applies again — no code changes.

---

## Putting the service on a container host instead

Railway, Render, Fly, or any VM with Docker. `docker-compose.yml` describes the whole stack.

```bash
docker compose up -d --wait          # the stack
uv run python -m scripts.seed        # a demo org, or --org yourco --name "Your Co"
uv run python -m workflows.worker    # the background jobs
```

`PLEXUS_CONSOLE_ORIGINS` and `GOOGLE_API_KEY` still apply.

---

## Preview mode

With no `NEXT_PUBLIC_PLEXUS_API` set, the hosted console falls back to a captured snapshot of an
example company and says so on every screen. It is read-only, because the writes it would
otherwise make belong to a service that is not there.

Preview is always a fallback, never a default: the console tries the real service first, so with
the stack running locally it talks to `http://localhost:8000` with nothing configured at all.

The snapshot in `dashboard/public/preview/` is real output from a real running system. Regenerate
it whenever the demo data or the screens change, and commit the result:

```bash
make up && make seed
uv run python -m scripts.export_snapshot
```

---

## Running everything locally

```bash
make up        # the stack
make seed      # the demo organisation
make worker    # background jobs, in another terminal
make console   # the console on :3000
make doctor    # checks all four and says what to fix
```
