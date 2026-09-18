# Compliance (GDPR and EU AI Act readiness)

Status: stub (Phase 0). Completed in Phase 4 with the pilot runbook.

## Data residency
All storage in the compose stack is local to the host running it. No cloud dependency is
required for development or the TCL pilot. Model calls to external vendors carry tokenised
content only (spec 06); the `sovereign` profile keeps model calls local as well.

## Data map
Generated from adapter `describe_schema()` output (Phase 1): for each source system, the fields
read, their PII hints, and where they land (documents, graph, event log).

## Records of processing
Exported as JSON from the data map plus the tenants table (Phase 1+).

## Logging and human oversight
- The Autonomy Ledger (append-only, hash-chained) and OpenTelemetry traces satisfy logging
  obligations for high-risk-adjacent use.
- Human oversight is structural: tiers, approver confirmation for promotion, verifier from a
  different vendor, kill switch at tenant and process level.

## Right to erasure
`DELETE /v1/tenants/{t}/subjects/{token}` (spec 06): vault entry erased, graph nodes marked
`erased`, documents purged, erasure logged.

## Retention
To be defined per tenant in Phase 4 (documents, event log, traces). The ledger is retained for
the life of the tenant.
