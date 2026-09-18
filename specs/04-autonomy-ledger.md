# Spec 04 — The Autonomy Ledger (Pillar 4)

Status: draft (Phase 0) · Phase: 3 · Source: brief §5 Pillar 4, §2 principle 4

## Purpose

Make autonomy earned, measurable, auditable, and reversible per process. The ledger is the
system's memory of every decision; the trust score and tier are derived from it and nothing else.

## Inputs

- Events from the action pipeline: shadow runs, suggestions, approvals, rejections, executions,
  reversals.
- Human decisions: promotion confirmations, manual overrides, pause/unpause.
- Config: trust weights, thresholds, sample sizes (`config/trust.yaml`).

## Outputs

- Append-only `ledger_entries` rows with a hash chain.
- Per-process `trust` score and `tier`.
- Kill-switch state (`paused`) at tenant and process level, exposed via API and dashboard.

## Data model changes

### Tiers

`OBSERVE` → `EXPLAIN` → `SUGGEST` → `ACT_WITH_APPROVAL` → `AUTONOMOUS` (Python `enum.IntEnum`
so ordering is explicit).

### Postgres

```sql
CREATE TABLE ledger_entries (
  seq         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id          uuid NOT NULL UNIQUE,
  tenant_id   text NOT NULL,
  process_id  text NOT NULL,
  entry_type  text NOT NULL CHECK (entry_type IN (
                'shadow_run','suggestion','approval','rejection','execution','reversal',
                'promotion','demotion','manual_override','refusal','pause','unpause')),
  actor       jsonb NOT NULL,          -- {kind: human|system|model, id, role?}
  payload     jsonb NOT NULL,
  trace_id    text NOT NULL,
  ts          timestamptz NOT NULL DEFAULT now(),
  prev_hash   text NOT NULL,           -- hash of previous entry for (tenant_id, process_id); genesis = 64 zeros
  hash        text NOT NULL            -- sha256(prev_hash || canonical_json(row without hash))
);
-- Append-only: UPDATE and DELETE are revoked from the application role and blocked by a trigger.
```

`process_state(tenant_id, process_id, tier, trust, paused, last_error_at, updated_at)` is a
derived cache; it can always be rebuilt from `ledger_entries`.
`tenant_state(tenant_id, paused, updated_at)`.

### Trust score (`core/ledger/trust.py`)

```
trust = w1 * approval_rate(last N)          # approvals / (approvals + rejections); 0 if none
      + w2 * (1 - reversal_rate(last N))    # reversals / executions; 0 reversals → 1
      + w3 * recency_factor(days_since_last_error)   # 1 - exp(-days / tau), tau = 14; no error → 1
      - w4 * blast_radius_penalty(process)  # mean blast_radius of last N simulations, 0..1
N = 30; weights default 0.4 / 0.3 / 0.2 / 0.1; result clamped to [0, 1]
```

Parameters live in `config/trust.yaml`. Changing the formula or weights requires sign-off
(brief §0.5d) and an ADR.

### Promotion and demotion (`core/ledger/tiers.py`)

- Promote one tier when `trust ≥ threshold[next_tier]` AND `samples(last N) ≥ min_samples[next_tier]`
  AND no `reversal` in the last 14 days AND an `approver` confirms. Never silent.
- Demote one tier immediately on any `reversal`. Demote to `OBSERVE` on any policy violation in
  an executed action. Both automatic, both ledger entries.
- Every promotion/demotion carries the inputs (trust, samples, thresholds) in `payload`.

### Kill switch

`paused` at tenant and process level. The executor reads both flags on every action (no caching
longer than 1 s) and refuses with a `refusal` ledger entry when either is set.

## Interfaces

```python
# core/ledger/ledger.py
async def append(entry: NewLedgerEntry) -> LedgerEntry            # computes prev_hash, hash
async def verify_chain(tenant_id: str, process_id: str) -> ChainStatus   # ok | broken_at(seq)
async def entries(tenant_id: str, process_id: str | None, filters: LedgerFilter) -> list[LedgerEntry]

# core/ledger/trust.py
def compute_trust(entries: Sequence[LedgerEntry], cfg: TrustConfig, now: datetime) -> TrustBreakdown

# core/ledger/tiers.py
def next_transition(state: ProcessState, breakdown: TrustBreakdown, cfg: TrustConfig) -> Transition | None
```

API:
- `GET /v1/tenants/{t}/ledger?process_id=&entry_type=&since=&until=` (paginated) and
  `GET .../ledger:export?format=jsonl|csv`.
- `GET /v1/tenants/{t}/ledger:verify` → chain status per process.
- `GET /v1/tenants/{t}/processes/{p}/trust` → `TrustBreakdown` and promotion eligibility.
- `POST /v1/tenants/{t}/processes/{p}:promote` (role `approver`) → ledger `promotion`.
- `POST /v1/tenants/{t}:pause|unpause`, `POST .../processes/{p}:pause|unpause` (role `approver`+).

## Failure modes

| Failure | Behaviour |
|---|---|
| Concurrent appends for one process | Serialised with `SELECT ... FOR UPDATE` on `process_state`; hash chain stays linear. |
| Hash mismatch on verify | Chain status `broken_at(seq)`, dashboard shows red, alert span emitted; nothing is auto-repaired. |
| `process_state` cache diverges | Rebuilt from ledger on startup and on verify. |
| Config weights do not sum sensibly | Loader rejects config at boot if any weight < 0 or w1+w2+w3 > 1. |

## Acceptance tests

- AT-04-1: 40 approvals and 1 reversal → score and tier follow the formula exactly (property
  tests with hypothesis over random entry sequences compared against a reference implementation).
- AT-04-2: Hash chain validation detects a tampered row (modify a payload via raw SQL as
  superuser, verify returns `broken_at`).
- AT-04-3: Executor refuses when paused and a `refusal` entry is appended.
- AT-04-4: `UPDATE`/`DELETE` on `ledger_entries` by the application role fails.
- AT-04-5: A promotion without an approver actor is rejected at the API and at the ledger layer.

## Open questions

- OQ-04-1: `recency_factor` shape is not specified in the brief. Recommendation:
  `1 - exp(-days/14)`, documented here; confirm before Phase 3.
- OQ-04-2: Should the hash chain be per `(tenant, process)` or per tenant? Recommendation: per
  process for cheap verification, plus a nightly tenant-wide Merkle root stored as its own entry.
