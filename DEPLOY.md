# Deploying Plexus

Plexus is two pieces: a console (Next.js) and a service (FastAPI, with Postgres, Neo4j, Redis
and Temporal behind it). The console is a thin client; every screen reads from the service.

That split matters for hosting. Vercel runs the console beautifully and cannot run the service,
so the service needs a home of its own before a hosted console shows anything.

## The console on Vercel

1. Import the repository at vercel.com/new.
2. **Set Root Directory to `dashboard`.** The console lives there, not at the repository root.
   Nothing else builds without this.
3. Add one environment variable:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_PLEXUS_API` | the public address of your Plexus service, for example `https://api.yourcompany.com` |

4. Deploy. The framework, build and install commands come from `dashboard/vercel.json`.

Without that variable the console still builds and loads, and says plainly that it cannot
reach its service rather than showing a broken page.

## The service

It needs Postgres, Neo4j, Redis and Temporal, so it belongs on something that runs containers:
Railway, Render, Fly, or a VM with Docker. `docker-compose.yml` describes the whole stack.

Once it is up:

```bash
docker compose up -d --wait        # the stack
uv run python -m scripts.seed      # the demo organisation, or --org yourco --name "Your Co"
uv run python -m workflows.worker  # the background jobs
```

Set `GOOGLE_API_KEY` for the service so it can write plain-language names and drafts. Without
it everything still works, using the built-in rules instead of a model.

The service must allow the console's origin. `api/main.py` currently allows `localhost:3000`;
add your Vercel domain there before deploying.

## Running it all locally

```bash
make up        # the stack
make seed      # the demo organisation
make worker    # background jobs, in another terminal
make console   # the console on :3000
make doctor    # checks all four and says what is wrong
```
