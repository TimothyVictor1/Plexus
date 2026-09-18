# Spec 11 — Security, tenancy, observability, compliance

Status: draft (Phase 0) · Phase: 0–4 · Source: brief §7, §3

## Purpose

Cross-cutting guarantees: every datum is scoped to a tenant, every actor is authenticated and
role-checked, every call is traced, and the deployment satisfies GDPR and EU AI Act logging and
human-oversight expectations.

## Inputs

- OIDC tokens from Keycloak (compose) or the customer's IdP.
- Tenant configuration (`tenants` table), adapter credentials (env + Docker secrets).

## Outputs

- `TenantContext` on every request, activity, and span.
- Structured JSON logs; OTel spans to Jaeger (dev) / OTLP (prod).
- `docs/compliance.md`, generated data map, records-of-processing export.

## Data model changes

- `tenants(id text PK, name, region 'EU', paused, created_at)`.
- Postgres roles: `plexus_app` (RLS enforced via `SET plexus.tenant_id`), `plexus_migrator`,
  `plexus_readonly`. Every table has `ENABLE ROW LEVEL SECURITY` and a policy
  `tenant_id = current_setting('plexus.tenant_id')`.
- Neo4j: every node/edge has `tenant_id`; `GraphStore` injects and checks the predicate.
- Redis: keys and streams prefixed `t:{tenant_id}:`.

## Interfaces

```python
# core/tenancy/context.py
class Role(StrEnum): viewer, operator, approver, admin     # ordered; higher includes lower
class TenantContext(BaseModel): tenant_id, subject, roles, trace_id
def require(role: Role) -> Dependency                       # FastAPI dependency
```

- `api/auth.py`: OIDC token validation (JWKS cached), maps realm roles → `Role`, rejects tokens
  without a tenant claim.
- `/v1/health/live` (process up) and `/v1/health` (deep: postgres, neo4j, redis, temporal,
  presidio analyzer/anonymizer; each `ok|degraded|down` with latency).
- Outbound network allow-list per adapter enforced in compose network policy and documented.
- Dependency scanning in CI (`uv export` → `pip-audit`; `pnpm audit`).
- Secrets: env in dev, Docker secrets in pilot; never in the repo (`detect-private-key` hook).

## Failure modes

| Failure | Behaviour |
|---|---|
| Request without tenant claim | 401. |
| Role below requirement | 403; audit log entry. |
| Cross-tenant query attempt | `GraphStore`/RLS return nothing; incident span emitted. |
| OTel exporter down | Spans buffered and dropped after limit; logs still structured. |

## Acceptance tests

- AT-11-1: RLS: with `plexus.tenant_id = 'a'`, rows for tenant `b` are invisible and
  un-insertable.
- AT-11-2: An `operator` token cannot call an `approver` endpoint (403).
- AT-11-3: Every span in a demo trace carries `tenant_id`.
- AT-11-4: `/v1/health` reports `down` for a stopped dependency and `ok` when restored.
- AT-11-5: CI dependency scan has no unresolved high-severity findings.

## Open questions

- OQ-11-1: Whether the pilot at TCL uses Keycloak or TCL's Google Workspace as IdP.
  Recommendation: Keycloak brokering Google, so RBAC stays in Plexus's control.
