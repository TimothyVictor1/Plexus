# Status

Read this at the start of every session. Update it at the end of every session.

## Current phase: 1 (partial) — the system runs end to end on fixtures

`make up && make seed && make console` gives a working Plexus against the Nordvik Konsult AB
fixtures. What follows is what is genuinely implemented, not what is planned.

### Working end to end (session 2, 2026-09-26)

**Ingestion and the graph (pillar 1, partial).** Fixture adapters for gmail, clickup and gdrive
feed 132 documents through the PII Boundary into Postgres and a Neo4j graph of 174 nodes and
264 edges, with provenance on every node. Re-seeding is idempotent: event ids are derived from
the source item, so nothing duplicates.

**PII Boundary (pillar 6).** Real and complete for the recogniser set in spec 06: email, IBAN,
Swedish personnummer and org number (both Luhn- and date-validated), phone, bankgiro, street
address, and person names from a per-tenant gazetteer persisted in Postgres. Tokens are
HMAC-derived, stable per tenant, format-preserving. The vault encrypts values with a per-tenant
key from the KMS abstraction. A 300-case hypothesis fuzz asserts no leaks and lossless restore.

**Event log and process mining (pillar 2, partial).** 132 object-centric events; cases are built
by union-find over shared object ids; a directly-follows graph plus a heuristic dependency
measure discovers the three ground-truth processes with the correct step order:

| Process | Steps | Cases | Median cycle |
|---|---|---|---|
| Enquiry to quote to invoice | 5 | 18 | 31.0 d |
| New-hire onboarding | 4 | 4 | 10.0 d |
| Monthly reporting | 3 | 6 | 2.2 d |

**Digital twin and policies (pillar 3, partial).** A safe rule engine over a fixed operator set,
no `eval`, dotted lookups on plain dicts only. Rules carry a scope, and a rule that cannot be
evaluated inside its scope fails closed. Blast radius is computed from the diff.

**Autonomy Ledger (pillar 4).** Append-only with a SHA-256 hash chain, a database trigger that
rejects UPDATE and DELETE, per-process advisory locking so the chain stays linear, and chain
verification that locates the exact broken row. The trust formula reads every parameter from
`config/trust.yaml`.

**Actor, verifier and the executor (pillar 5).** The full pipeline runs: plan, simulate, verify,
gate, record. The executor is the only module that calls an adapter write or restores a token,
enforced by an AST test over every file, and `executions.verdict_id` is NOT NULL so an execution
cannot exist without a verdict. Every gate path is covered by integration tests: low tiers never
write, act-with-approval needs a person, escalate outranks the tier, a blocking policy is
refused, and the kill switch refuses everything and records the refusal.

**Operator console.** Next.js 15, Swedish and English, seven pages against the live API:
Overview, Processes, Inbox, Graph, Ledger, PII boundary, Adapters. The role selector is real:
the API enforces it, so a viewer genuinely cannot approve.

### Verification (2026-09-26, macOS, Docker 28.3)
- `make lint`: ruff clean, ruff format clean, mypy strict clean (86 files), compose valid,
  dashboard eslint + tsc + i18n parity clean.
- `make test`: 119 passed (unit, architecture, property-based).
- `PLEXUS_INTEGRATION=1 uv run pytest -m integration`: 17 passed against the live stack.
- `make up`: 10/10 services healthy. `make seed`: 132 documents, 31 vault entries, 3 processes.

## Deliberately not built yet

- **Hosted model vendors.** `config/models.yaml` still names anthropic and openai, and the
  router still refuses to boot in production when they match. Every role currently resolves
  through `core/models/providers/local.py`, a deterministic rule-based provider, so the pipeline
  runs with no API key and nothing leaves the laptop. Wiring the Anthropic and OpenAI providers
  is the next piece of Phase 1 and needs the decisions in QUESTIONS.md answered first.
- **Extraction by model.** Entities come from adapter structure, not from an extraction agent.
  Spec 01 step 2 (embedding similarity, LLM adjudication) is not built, so AT-01-1 is unmeasured.
- **Explain agent, Temporal workflows, OIDC, Redis streams, immune system, adapter generator.**
  Specified, not implemented. The console's role selector stands in for OIDC.
- **Presidio containers** run in compose but the boundary does not call them; the local
  recognisers cover the spec's list and always work. Layering Presidio on additively is a small
  change in `core/pii/boundary.py`.

## Decisions made this session

- The fixture adapter writes to an `adapter_records` table, so an execution is observable
  without touching anyone's real Gmail or ClickUp. It satisfies the adapter contract in full.
- The vault uses a Blake2b keystream rather than AES-GCM, to keep the pilot free of a crypto
  dependency. The interface (per-tenant data key, nonce, key_version) is the real one, so
  swapping in AES-256-GCM is a change inside `core/pii/vault.py`. Logged as OQ-06-3.
- Policy rules carry an explicit scope. Fail-closed on an absent field is correct per spec 03,
  but only inside the rule's scope; a spending limit must not judge an action with no money.
- `RoleRequired` and `WritePathNotImplemented` were renamed with an `Error` suffix (ruff N818).
- Seeded Swedish identity numbers are generated with real Luhn check digits, because the
  recognisers validate them. An invented number is silently ignored, which would hide a leak.

## Next
1. Anthropic and OpenAI providers behind the router, with cost accounting and the boot-time
   model check. Needs OQ-09-1 and OQ-09-2 answered.
2. The extraction agent and the Explain agent, then measure AT-01-1 and AT-01-2.
3. Move ingestion and the pipeline into Temporal workflows (principle 7).
4. OIDC through Keycloak, replacing the console's role selector.
