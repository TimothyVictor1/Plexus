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

## Session start
Read this file, docs/STATUS.md, docs/QUESTIONS.md, and the spec for the pillar you
are working on. State the session plan in at most 10 bullets, then execute.
The full build brief lives in PLEXUS_BUILD_PROMPT.md; specs/ are derived from it and
are what you implement from.
