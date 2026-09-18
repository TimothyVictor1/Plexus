# Spec 08 — Self-extending adapter generator (Pillar 8)

Status: draft (Phase 0) · Phase: 4 · Source: brief §5 Pillar 8

## Purpose

For a system with no adapter, generate an MCP server implementing `PlexusAdapter` from its API
spec or database schema, test it in a sandbox, and hand it to a human for review. Never enable
writes by default.

## Inputs

- One of: OpenAPI/GraphQL spec URL, read-only Postgres/MySQL connection string, or a short
  description plus example payloads.
- The adapter contract and conformance suite (`adapters/_contract/`).

## Outputs

- A generated adapter package under `adapters/generated/{id}/` (code, tests, README, event
  mappings), with `capabilities.write = False`.
- Conformance results from an isolated container run.
- A review object in the dashboard (diff, test results, detected schema, proposed event mappings).

## Data model changes

- `adapter_generations(id, tenant_id, input_kind, input_ref, status running|passed|failed|approved|rejected,
  attempts, conformance jsonb, diff_ref, decided_by, trace_id, created_at)`

## Interfaces

- `adapters/generator/loop.py`: explicit coding-agent loop using router role `actor` with tools
  `read_spec`, `write_file`, `run_conformance`. Max `config.generator.max_iterations` iterations;
  each iteration's diff and test output recorded.
- `adapters/generator/sandbox.py`: runs conformance in a container with network allow-list
  limited to the target system, read-only credentials, sandbox tenant.
- `adapters/_contract/conformance/`: pytest suite parameterised by adapter id: `describe_schema`
  shape, `backfill` yields valid `SourceItem`s with tokenised actors, `read` round-trip, `watch`
  optional, `write` raises `WriteDisabled` unless enabled by an `admin`.
- API: `POST /v1/adapters/generate`, `GET /v1/adapters/generations/{id}`,
  `POST .../generations/{id}:approve` (role `admin`), `POST /v1/adapters/{id}/write:enable`
  (role `admin`, ledger-like audit row).

## Failure modes

| Failure | Behaviour |
|---|---|
| Spec unreachable or invalid | Generation fails fast with a parse report. |
| Conformance fails after max iterations | Status `failed`, artifacts kept for human debugging. |
| Generated code imports `core.action.executor` or sets `write=True` | Static check fails CI and the review object is blocked. |
| Sandbox container escapes allow-list | Network policy denies; finding routed to the immune system. |

## Acceptance tests

- AT-08-1: Given `scripts/fixtures/openapi/invoicing.yaml`, the generator produces an adapter
  passing backfill/read conformance without human edits in ≥ 3 of 5 runs.
- AT-08-2: Static check: generated adapters cannot import `executor` or expose `write` as
  enabled by default (CI).
- AT-08-3: `write:enable` without role `admin` is rejected.

## Open questions

- OQ-08-1: Container runtime for the sandbox on a laptop (Docker-in-Docker vs. sibling
  containers via the host socket). Recommendation: sibling containers with a dedicated network,
  documented in the runbook.
