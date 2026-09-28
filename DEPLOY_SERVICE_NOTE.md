# Configuring the two services on a container host

This repository holds two deployables:

- the **service** — Python, built from `Dockerfile` at the repository root
- the **console** — Next.js, in `dashboard/`

Neither has a config file at the repository root, and that is deliberate. A `railway.json` there
is applied to *every* service in the project, including the one whose root directory is
`dashboard/` — which then tries to build the Python Dockerfile against the console's directory
and fails on the first `COPY` of a path that only exists at the repository root.

So each service is configured on the service itself:

## plexus-service

| Setting | Value |
|---|---|
| Root Directory | *(empty — the repository root)* |
| Builder | Dockerfile (auto-detected from `Dockerfile`) |
| Healthcheck | `/v1/health/live` — answers without touching Postgres |
| Port | assigned by the host as `$PORT`; the Dockerfile reads it |

## plexus-console

| Setting | Value |
|---|---|
| Root Directory | `dashboard` |
| Builder | Nixpacks (auto-detected from `package.json`) |
| Build | `pnpm install --frozen-lockfile && pnpm run build` |
| Start | `pnpm start -p $PORT` |
| Healthcheck | `/en` |

`NEXT_PUBLIC_PLEXUS_API` must be set on the console **before** it builds: Next bakes
`NEXT_PUBLIC_*` values into the bundle at build time, so changing it later does nothing until
the console is rebuilt.

## The scheduled work

The service replaces the Temporal schedule with an HTTP cron when `JOBS_SCHEDULER=cron`:

| Path | Schedule |
|---|---|
| `/v1/jobs/maintenance` | every 6 hours |

It authenticates with the `CRON_SECRET` variable, and refuses outright when none is set.
