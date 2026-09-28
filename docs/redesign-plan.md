# Plexus redesign plan

Target: `design/plexus-redesign-mockup.html`. Awaiting sign-off before any code is written.

Rule this plan follows: extend what exists, never rewrite it. Nothing ships in the UI that is
not backed by a real endpoint reading real rows.

---

## 0. What already exists and is reused unchanged

| Area | Module | Reused how |
|---|---|---|
| Tenancy and RBAC | `core/tenancy` | Unchanged. Already correct. |
| Postgres access, RLS | `core/db` | Unchanged. New tables follow the same RLS pattern. |
| PII boundary and vault | `core/pii` | Unchanged. Becomes the masking layer for every LLM call. |
| Event log | `core/events` | Unchanged shape. Connectors write into it. |
| Process miner | `agents/discover/miner.py` | Kept. One bug fixed (bottleneck). |
| Graph store | `core/graph` | Kept, moves behind Settings › Advanced. |
| Ledger and hash chain | `core/ledger/ledger.py` | Unchanged. Every level change and execution still writes here. |
| Policy engine and twin | `twin/` | Unchanged. Still gates every action. |
| Action pipeline and executor | `core/action` | Kept. Review items wrap `proposed_actions`; the executor stays the only write path. |
| Model router | `core/models` | Kept. Gains real providers behind the existing interface. |

## 1. Bugs confirmed by inspection

| # | Bug | Evidence | Fix |
|---|---|---|---|
| 1 | Trust scores 0.50 with zero decisions | `compute_trust([])` returns 0.5: the reversal and recency terms pay out in full for a process with no history | Ramp both terms by `min(1, decisions / min_decisions_for_credit)` |
| 2 | Bottleneck returns a step, not a transition | `miner.py:163` uses `max(edges, …).target` | Return `{from, to, median}`; rename the metric key |
| 3 | Promote ignores trust entirely | `api/routers/actions.py` increments the tier with no check | Server-side gate: trust ≥ threshold AND decisions ≥ required AND not paused AND role ≥ admin |

## 2. Data model changes

All migrations are additive. No existing table is dropped or altered destructively.

**`004_org.sql`** — extend `tenants`: `locale text not null default 'en'`, `is_demo boolean not null default false`, `display_name text`. Backfill existing rows.

**`005_language.sql`**
- `label_overrides(tenant_id, kind, target_id, text, author, created_at)` — user corrections, highest precedence.
- `label_cache(tenant_id, kind, signature, text, source, model, created_at)` — LLM or rule output, keyed by process structure signature so it regenerates when the structure changes.

**`006_review.sql`**
- `review_items(id, tenant_id, process_id, action_id → proposed_actions, kind, title, why, draft_structured jsonb, draft_text, approve_label, status, created_at, decided_by, decided_at, result jsonb, error)`.
  `status ∈ open | approved | edited | skipped | executed | failed`. Wraps an existing `proposed_action` rather than duplicating it.
- `triggers_seen(tenant_id, process_id, dedupe_key, created_at)` — idempotency, so a trigger fires once per real-world occurrence.

**`007_connections.sql`**
- `connections(id, tenant_id, category, provider, status, last_sync, scopes jsonb, config jsonb, created_at)`.
- `documents` and `event_log` gain a nullable `connection_id` so disconnect can detach or purge by source.

**`008_ask.sql`**
- `conversations(id, tenant_id, user_id, title, created_at)`, `messages(id, conversation_id, role, text, sources jsonb, created_at)`.
- Full-text index: `documents.search_tsv` generated column + GIN index over the tokenised body and title.

**`009_insights.sql`** — `insights(id, tenant_id, rank, kind, text, sub, health, process_id, computed_at)`.

**`010_jobs.sql`** — `job_runs(id, tenant_id, job, status, started_at, finished_at, detail)` for observability of background work.

## 3. Services (new, under `core/` and `agents/`)

- **`core/org/service.py`** — org record, onboarding stage. Stage is `no_connections` when zero connections, `learning` when connected but no process meets `ready_min_cases`, else `ready`. Threshold in config.
- **`core/language/service.py`** — the plain-language layer. Resolution order: override → cache → rule-based fallback. Rule fallback is a verb-pair phrase table (`created → invoiced` becomes "Sending the invoice after the work is done"). The LLM sees only structure: verb names, tool names, counts, durations. Never document text, never a name.
- **`core/language/format.py`** — durations to "about 2 days" server-side; every duration also returned raw.
- **`core/processes/service.py`** — assembles the process list and detail: health, level, slowest transition, tools, help tip. Health from bottleneck share of total cycle, thresholds in `config/processes.yaml`.
- **`agents/triggers/`** — trigger definitions and evaluation. Three real ones on demo data: invoice overdue, routine repeat order pending, report ready. Each produces a `ProposedAction` through the existing actor, then a `review_item` with a drafted message.
- **`core/ask/retrieval.py`** — Postgres full-text over documents plus event aggregates, returning passages with their `source_ref`. No embeddings in slice one; pgvector is already installed if retrieval quality needs it later.
- **`core/ask/service.py`** — retrieve, mask, compose, stream, cite. Refuses to answer when retrieval is empty rather than guessing.
- **`core/insights/service.py`** — ranks biggest bottleneck, biggest change against the previous period, and one thing running smoothly.
- **`adapters/connectors/`** — connector registry: `category, provider, status, connect(), disconnect(), sync()`. The demo connector is real. Every third-party provider implements the same interface and reports `not_configured` until credentials exist.

## 4. Endpoints (all under `/v1`, all tenant-scoped, all role-checked)

| Method | Path | Notes |
|---|---|---|
| GET | `/org/status` | stage, connectedCount, processCount, reviewCount |
| GET | `/home` | one call for Home: stage, greetingName, top 3 reviews, insights, top 4 tools, counts |
| GET | `/processes?filter=slow` | list shape from B3 |
| GET | `/processes/{id}` | detail: steps, waits, helpTip, autonomy, technical |
| PATCH | `/processes/{id}` | rename process; `PATCH /processes/{id}/steps/{n}` renames a step |
| POST | `/processes/{id}/promote` \| `/demote` \| `/pause` \| `/resume` | gated; refusal returns a human reason |
| GET | `/review?status=open\|done_today` | |
| POST | `/review/{id}/approve` | optional edited draft; executes through the executor |
| POST | `/review/{id}/skip` | counts as a rejection for trust |
| POST | `/ask` | SSE stream; returns sources |
| GET | `/ask/suggestions` | 3 questions from current insights |
| GET | `/ask/conversations`, `/ask/conversations/{id}` | history |
| GET | `/insights` | top 3 |
| GET | `/connections` | grouped by category |
| POST | `/connections/{provider}/connect`, `/connections/{id}/disconnect` | |
| GET | `/settings/advanced/*` | existing graph and ledger routes, re-pathed |

Existing `/overview`, `/inbox`, `/adapters`, `/pii/tokenise`, `/ledger` stay live so nothing breaks mid-migration; they are removed only in the final slice.

## 5. Background jobs

Temporal is already in compose and unused. A worker process (`workflows/worker.py`, `make worker`) runs:

| Job | Schedule | Work |
|---|---|---|
| `sync_connections` | every 15 min | pull from each connected source into the event log |
| `mine_processes` | after sync, incremental | re-run the miner, refresh labels when the signature changes |
| `check_triggers` | every 10 min | evaluate triggers, create review items for processes at level ≥ 3 |
| `recompute_insights` | hourly and after mining | refresh the insights table |

This satisfies ENGINEERING.md principle 7 and B10. The action pipeline's wait-for-approval becomes a Temporal signal in slice (d).

## 6. Frontend

**Theme.** `globals.css` tokens replaced with the mockup palette, dark only: ground `#040405`, panels `#09090B`, cards `#101013`, raised `#16161A`/`#18181C`, borders `#1C1C21`/`#202025`, text `#F2F2F3`, muted `#A1A1A8`, accent `#5EEAD4` with `#040405` on it. Status pairs good/could-be-faster/slow, each always with a text label, never colour alone. Plus Jakarta Sans 400–800. Focus ring 2px accent. Targets ≥44px.

**Shell.** `components/shell/AppShell.tsx` wraps a 68px icon rail and the main panel, 10px outer gap, 16px radii. Rail: mark, accent "+" to Ask, then Home, Ask, Your work, To review (badge `#FB7185`), Connections, Settings pinned bottom. Every button has `aria-label` and a tooltip. Top bar carries org name, "Example data" badge when `is_demo`, Invite team, avatar menu holding the role selector.

**Routes.**

| Old | New |
|---|---|
| `/[locale]` overview | `/[locale]` Home |
| — | `/[locale]/ask` |
| `/[locale]/processes` | `/[locale]/work`, `/[locale]/work/[id]` |
| `/[locale]/inbox` | `/[locale]/review` |
| `/[locale]/adapters`, `/[locale]/boundary` | `/[locale]/connections` |
| `/[locale]/graph`, `/[locale]/ledger` | `/[locale]/settings/advanced` |

Old paths become locale-aware permanent redirects in `next.config.ts`.

**Components.** `StatusChip`, `LevelBars` (5 bars), `WaitTimeline` (bars scaled by duration, slowest highlighted), `ReviewCard`, `ToolCard`, `InsightRow`, `AskThread`, `TechnicalDetails` (collapsed by default), `EmptyState`.

**Copy.** Every string in `messages/en.json`, mirrored into `sv.json`; the existing parity check keeps them in step. Banned from default views: mined, event log, dependency, variants, rung, trust score, blast radius, PII, adapters, actors. A lint script greps the message files for those words outside the `technical.*` namespace and fails CI.

## 7. Slice order

Each slice ends with migrations run, tests green, pages checked at `localhost:3000/en/…`, and one commit.

- **a. Foundation** — theme, shell, org model, `/org/status`, generic demo seed, route redirects.
- **b. Your work** — processes API, plain-language layer, bottleneck fix, list and detail pages.
- **c. Autonomy** — trust fix, gated promote/demote/pause, ladder UI, ledger entries.
- **d. To review** — review items, three triggers, approve/edit/skip, execution, badge.
- **e. Home** — `/home` and `/insights`, three onboarding states.
- **f. Ask** — retrieval, streaming, sources, suggestions, rate limit.
- **g. Connections** — connector framework, connect/disconnect, privacy section from config.

## 8. What will be stubbed, and why

1. **Third-party OAuth.** No credentials exist for Gmail, Outlook, HubSpot, Fortnox, Visma, Slack or ClickUp. Every provider implements the connector interface; without credentials each reports `not_configured` and the Connect button explains what is missing. The demo connector is fully real. Marked TODO per provider.
2. **Outbound email.** No SMTP is configured, so "Invite team" creates a real invite row and shows a copyable link; it does not send mail. TODO.
3. **Real writes to customer systems.** Approving a review item executes through the existing executor into the fixture adapter, which is a real write to a real table. It becomes a real third-party write the moment a connector has credentials, with no pipeline change.
4. **Review badge** polls every 30 seconds. SSE is a later optimisation.

## 9. Testing

Unit: trust at 0 / few / reversal / error / blast radius, bottleneck transition, health thresholds, duration formatting, plain-language fallback chain, trigger dedupe.
API integration: every endpoint against the demo seed.
End to end: seed → Home shows 3 reviews → approve one → badge drops to 2 → ledger contains the entry with actor and timestamps.
Plus the existing 136 tests, which must stay green.
