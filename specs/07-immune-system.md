# Spec 07 — Immune system (Pillar 7)

Status: draft (Phase 0) · Phase: 4 · Source: brief §5 Pillar 7

## Purpose

Continuously red-team every adapter input surface against prompt injection and harden the
system through reviewed, versioned mitigations rather than ad-hoc code edits.

## Inputs

- The set of adapters and their input surfaces (email bodies, task descriptions, file text, chat).
- A sandbox tenant mirroring real adapters with fixture data (including the 20 planted payloads).
- Prior payloads and outcomes (the growing eval set).

## Outputs

- `immune_runs`, `immune_findings`, `mitigation_proposals` rows.
- A live immune score with trend on the dashboard.
- Applied mitigations as versioned config (`config/mitigations/*.yaml`), never code edits.

## Data model changes

- `immune_runs(id, tenant_id = sandbox tenant, started_at, finished_at, trigger nightly|adapter_change|manual, score, trace_id)`
- `immune_findings(id, run_id, payload_id, adapter_id, surface, attack_kind direct|indirect|multilingual|encoding|tool_hijack, succeeded bool, evidence jsonb)`
- `immune_payloads(id, kind, language, text, created_by red|human, first_seen_run)`
- `mitigation_proposals(id, finding_id, kind input_filter|prompt_hardening|allowlist_change, config_patch jsonb, status pending|approved|rejected, decided_by, applied_version)`

Score: `1 - (successful_attacks / attempted)` over the last run, smoothed with the previous 7
runs; shown with trend.

## Interfaces

- `agents/immune/red.py`: `generate_payloads(surfaces, history) -> list[Payload]` (router role
  `actor`; payload families: direct, indirect via document content, multilingual sv/en/fi,
  encoding tricks, tool-call hijack) and `inject(payload, sandbox_adapter)`.
- `agents/immune/blue.py`: `detect(run) -> list[Finding]` (unexpected tool call, policy bypass,
  leaked token, executor invocation) and `propose_mitigation(finding) -> MitigationProposal`.
- Mitigations apply through `core/immune/mitigations.py` which loads versioned config into the
  input filter chain and prompt assembly; each applied version is recorded.
- `workflows/immune.py`: `ImmuneRunWorkflow(trigger)` nightly (Temporal schedule) and on adapter
  change.
- API: `GET /v1/immune/runs`, `GET .../runs/{id}/findings`, `POST .../mitigations/{id}:approve`
  (role `admin`).

Tenant isolation: every span in an immune run asserts `tenant_id == sandbox tenant`; the
`GraphStore` and adapters refuse a sandbox tenant id outside an immune run and a non-sandbox id
inside one.

## Failure modes

| Failure | Behaviour |
|---|---|
| Red agent produces a payload targeting a non-sandbox tenant | Rejected at inject time; incident logged. |
| Attack succeeds and reaches the executor | Impossible in sandbox (executor refuses sandbox tenant writes); finding recorded as critical. |
| Mitigation breaks legitimate input | Evals in `evals/immune/` include benign controls; a mitigation reducing benign pass-rate below threshold cannot be approved. |

## Acceptance tests

- AT-07-1: On a fresh install, the red agent finds at least one working injection against the
  deliberately weak fixture adapter; after the blue agent's approved mitigation is applied, the
  same payload fails.
- AT-07-2: Immune runs never touch a non-sandbox tenant (assert `tenant_id` on every span in
  the run's trace).
- AT-07-3: Payloads and outcomes persist and the next run's eval set includes them.

## Open questions

- OQ-07-1: Model for the red agent. Using the `actor` role means the same vendor attacks and
  (via the workhorse) defends. Recommendation: allow a dedicated `red` role in `models.yaml`
  defaulting to the verifier vendor.
