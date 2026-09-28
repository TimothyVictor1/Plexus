# Deploying Plexus

Plexus is two pieces:

- **the console** — Next.js, in `dashboard/`. A thin client. It holds no data.
- **the service** — FastAPI, with Postgres, Neo4j, Redis and Temporal behind it. Everything
  real happens here.

That split decides how it is hosted. Vercel runs the console very well and cannot run the
service, because the service needs databases and a worker that stay running.

## Putting the console on Vercel

1. Import the repository at [vercel.com/new](https://vercel.com/new).
2. **Set Root Directory to `dashboard`.** The console lives there, not at the repository root.
   Nothing builds without this.
3. Deploy.

That alone gives you a working link, in **preview mode**: the console serves a captured
snapshot of an example company and says so at the top of every screen. It is read-only,
because the writes it would otherwise make belong to a service that is not there.

To make it your own company's console, add one environment variable and redeploy:

| Name | Value |
|---|---|
| `NEXT_PUBLIC_PLEXUS_API` | the public address of your Plexus service, e.g. `https://api.yourcompany.com` |

The moment that is set, preview mode switches off and every screen reads live.

## Putting the service somewhere

It needs Postgres, Neo4j, Redis and Temporal, so it wants a host that runs containers:
Railway, Render, Fly, or any VM with Docker. `docker-compose.yml` describes the whole stack.

```bash
docker compose up -d --wait          # the stack
uv run python -m scripts.seed        # a demo org, or --org yourco --name "Your Co"
uv run python -m workflows.worker    # the background jobs
```

Two settings matter once it is public:

| Variable | Why |
|---|---|
| `PLEXUS_CONSOLE_ORIGINS` | your Vercel domain, so the browser is allowed to call the service |
| `GOOGLE_API_KEY` | plain-language names and drafted messages. Without it everything still works, using built-in rules |

## Refreshing the preview snapshot

The snapshot in `dashboard/public/preview/` is real output from a real running system, written
once by a script. Regenerate it whenever the demo data or the screens change:

```bash
make up && make seed
uv run python -m scripts.export_snapshot
```

Commit the result. Nothing in it is invented; it is the same JSON the service returns.

## Running everything locally

```bash
make up        # the stack
make seed      # the demo organisation
make worker    # background jobs, in another terminal
make console   # the console on :3000
make doctor    # checks all four and says what to fix
```
