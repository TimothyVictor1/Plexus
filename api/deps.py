"""Request dependencies: tenant context and role gating (spec 11).

OIDC via Keycloak lands with the auth work; until then the console runs as a dev principal
whose role is taken from a header, so every role check on the path is exercised for real.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, Header, HTTPException

from core.tenancy import Role, RoleRequiredError, TenantContext, require


async def tenant_context(
    x_plexus_tenant: str = Header(default="nordvik"),
    x_plexus_subject: str = Header(default="dev-approver"),
    x_plexus_role: str = Header(default="approver"),
) -> TenantContext:
    try:
        role = Role.parse(x_plexus_role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return TenantContext(
            tenant_id=x_plexus_tenant,
            subject=x_plexus_subject,
            roles=frozenset({role}),
            trace_id=str(uuid.uuid4()),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def needs(role: Role) -> Callable[..., Awaitable[TenantContext]]:
    async def _dep(ctx: TenantContext = Depends(tenant_context)) -> TenantContext:
        try:
            require(ctx, role)
        except RoleRequiredError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        return ctx

    return _dep
