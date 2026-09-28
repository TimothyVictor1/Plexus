"""The Plexus service, as a single serverless function.

Locally, `api.main:app` runs under uvicorn next to Postgres, Neo4j, Temporal and the rest of the
Compose stack. A serverless host gives none of that: no worker that stays alive, no second
database, and many short-lived copies of this process sharing one Postgres.

None of that changes the product. Everything a person uses — what needs them, the ways work gets
done, the what-if model, the questions and their sources, the review queue, the connections — is
answered from Postgres and the event log. What the missing pieces cost is written down here
rather than hidden, and each one is configuration, not a second code path:

* the graph store, so the audit screen's map says there is none instead of failing
  (GRAPH_ENABLED=false)
* Temporal, so the schedule becomes an HTTP cron calling the same job functions
  (JOBS_SCHEDULER=cron, and a POST to /v1/jobs/maintenance with PLEXUS_CRON_SECRET)
* a big connection pool, because a hundred copies of this asking for ten connections each
  would exhaust a managed Postgres (POSTGRES_POOL_MAX, and a pooling connection string)

Deployed via `[tool.vercel] entrypoint = "service:app"` in pyproject.toml.
"""

from __future__ import annotations

import os
from pathlib import Path

# Several modules read their configuration by a path relative to the working directory
# (`config/models.yaml`, `config/trust.yaml`, `config/processes.yaml`). Locally that directory
# is wherever you ran the command from, which is the repository root. A host picks its own, so
# anchor to this file before importing anything that reads one.
os.chdir(Path(__file__).resolve().parent)

from api.main import app  # noqa: E402 - must follow the chdir above

__all__ = ["app"]
