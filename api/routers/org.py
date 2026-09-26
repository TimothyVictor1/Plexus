"""Organisation and onboarding state."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import tenant_context
from core.org import Org, OrgStatus, get_org, org_status
from core.tenancy import TenantContext

router = APIRouter(tags=["org"])


@router.get("/org", response_model=Org)
async def org(ctx: TenantContext = Depends(tenant_context)) -> Org:
    found = await get_org(ctx.tenant_id)
    if found is None:
        raise HTTPException(404, f"no organisation {ctx.tenant_id}")
    return found


@router.get("/org/status", response_model=OrgStatus)
async def status(ctx: TenantContext = Depends(tenant_context)) -> OrgStatus:
    return await org_status(ctx.tenant_id)
