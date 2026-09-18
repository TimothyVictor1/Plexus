# Spec 10 — Dashboard

Status: draft (Phase 0) · Phase: 1–4 (pages by phase) · Source: brief §8, §3, §7

## Purpose

A calm, dense, professional operator UI for the whole system, accessible (AA), Swedish and
English from day one, mobile-usable for the Inbox.

## Inputs

- The `/v1` API (OpenAPI generated; client types generated from it).
- OIDC login via Keycloak; roles from the token.

## Outputs

Pages, by phase:

| Page | Phase | Content |
|---|---|---|
| Overview | 1 | tenant health, immune score, cost, tier distribution |
| Graph | 1 | React Flow explorer with provenance drawer |
| Ask | 1 | Explain agent chat with cited subgraph |
| Adapters | 1 | connected systems; generator wizard and review queue (4) |
| Processes | 2 | swimlane/DFG views, metrics, variant merge, tier badge, promote/pause |
| Policies | 2 | rule editor (structured fields, no free-text expressions) |
| Inbox | 3 | suggestions/approvals with proposal, simulation report, verdict; approve/reject/reverse |
| Ledger | 3 | filterable, exportable, hash-chain status |
| Ontology | 4 | proposals awaiting approval |
| Immune | 4 | runs, findings, mitigations, score trend |

## Data model changes

None server-side. Client state is per-page; no client-side caching of PII (there is none, only
tokens; tokens are displayed as-is with a hover showing entity type).

## Interfaces

- Next.js 15 App Router, server components by default; client components only for React Flow,
  forms, and the Inbox actions.
- `dashboard/messages/{sv,en}.json` with `next-intl`; every user-facing string goes through it.
- `dashboard/lib/api.ts`: typed client generated from `/v1/openapi.json` (`openapi-typescript`).
- Role gating: `approver` for approve/reject/promote/pause controls, `admin` for adapter write
  enablement and mitigations; server-side check on every action (the UI only hides).
- The kill switch is a prominent red control on Overview and each Process page.

## Failure modes

| Failure | Behaviour |
|---|---|
| API down | Overview shows dependency status from `/v1/health`; pages degrade to cached read views. |
| Token expired | Redirect to Keycloak; unsaved Inbox decision preserved in session storage. |
| Large graph | Explorer paginates by neighbourhood depth; never loads the whole tenant graph. |

## Acceptance tests

- AT-10-1: Playwright: login as `dev-approver`, open Inbox, approve an item, see it in the Ledger.
- AT-10-2: Every string in `app/` resolves in both `sv.json` and `en.json` (lint script).
- AT-10-3: axe-core AA checks pass on every page in CI.
- AT-10-4: Inbox page usable at 375px width (Playwright mobile project).

## Open questions

- OQ-10-1: Use shadcn/ui as specified, or keep to plain Tailwind to reduce surface. Recommendation:
  shadcn/ui for forms, dialogs, tables; nothing else.
