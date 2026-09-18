# Status

Read this at the start of every session. Update it at the end of every session.

## Current phase: 0 — Skeleton

### Done (session 1, 2026-09-18)
- Repo initialised, layout from brief §4 created, `CLAUDE.md` installed.
- `pyproject.toml` (uv, ruff, mypy strict, pytest, hypothesis), `Makefile`, pre-commit.
- `docker-compose.yml`: Postgres 16 + pgvector, Neo4j 5, Redis 7, Temporal + UI, Jaeger,
  Keycloak (realm with viewer/operator/approver/admin), Presidio analyzer + anonymizer, API.
- All 12 specs drafted under `specs/` with the required sections and open questions.
- Phase 0 code: settings, tenancy context + RBAC, adapter contract types, `/v1/health` deep
  checks, executor placeholder (refuses until Phase 3).
- Architecture tests enforcing: vendor SDKs only in `core/models/providers`, no agent
  frameworks, PII `restore` only in executor, adapter `write` only in executor, no `eval` in
  `twin/`, all specs and packages present.
- CI (GitHub Actions): lint, type-check, tests, compose validation, dashboard lint.
- Dashboard skeleton: Next.js 15, i18n `sv`/`en`, Overview placeholder.
- Docs: architecture (Mermaid), ADR-0001 (single write path), compliance stub, questions.

### Phase 0 Definition of Done
`make up && make test` green on a clean machine. See the bottom of this file for the latest run.

## Next (Phase 1 — Ingest + Graph + Explain, weeks 1–3)
1. `core/models/router.py` + Anthropic/OpenAI/local providers, cost table, prompt loader, boot-time
   model verification (spec 09). Resolve OQ-09-1/2 first.
2. `core/pii/boundary.py` + recognisers + vault + fuzz suite (spec 06).
3. Postgres migrations (documents, chunks, ontology_proposals, corrections, model_calls, RLS).
4. `core/graph/` schema, store abstraction (Neo4j + Kùzu), `apply.py` (spec 01).
5. Adapter base class with enforced tokenised emission; gmail, clickup, gdrive adapters against
   fixtures; conformance suite.
6. Nordvik Konsult AB fixture generator and labels (brief §11).
7. Extraction agent, Explain agent, eval harness v1, `evals/model_selection.md`.
8. Dashboard: Overview, Graph, Ask, Adapters pages.
9. `scripts/demo_phase1.sh`.

## Decisions made
- Flat Python packages at repo root, `uv` with `package = false`; tests run with `pythonpath=.`.
- Health checks are TCP/HTTP reachability in Phase 0; client-level in Phase 1.
- Neo4j APOC enabled in compose; Temporal uses the same Postgres instance (separate DBs).
- Keycloak dev realm ships two users: `dev-admin` / `dev-approver` (passwords equal usernames).
- Jaeger pinned to `jaegertracing/all-in-one:1.76.0` (the brief did not pin; `1.62` no longer
  exists on Docker Hub). Jaeger v2 (`jaegertracing/jaeger`) is a Phase 4 consideration.
- Temporal auto-setup runs with its built-in dynamic config (the image ships no
  `development-sql.yaml`).
- ruff 0.16 formats Python code blocks inside Markdown; `*.md` is excluded so specs and the brief
  stay verbatim.
- Presidio images are `latest` for Phase 0; Phase 1 pins a digest and builds the Swedish-model
  analyzer image (docs/QUESTIONS.md concern 2).
- pnpm is invoked through `npx pnpm@9.15.0` when not on PATH (`corepack enable` needs sudo on
  this machine); the Makefile handles both.

## Latest local verification (2026-09-18, macOS, Docker 28.3)
- `make up`: 10/10 services healthy (postgres, neo4j, redis, temporal, temporal-ui, jaeger,
  keycloak, presidio-analyzer, presidio-anonymizer, api). First boot pulled all images in roughly
  25 minutes on a slow connection.
- `GET /v1/health` from the host: HTTP 200, all six dependencies `ok`, latencies 15–27 ms.
- `make lint`: ruff clean, ruff format clean, mypy strict clean (49 files), compose config valid,
  dashboard eslint + tsc + i18n parity clean.
- `make test`: 69 passed (unit + architecture).
- `pnpm build` (dashboard): succeeds; `/sv` and `/en` prerendered.
- Not yet exercised: GitHub Actions itself (no remote configured); `pip-audit` step runs in CI only.
