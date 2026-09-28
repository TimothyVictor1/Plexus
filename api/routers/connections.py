"""The tools a company has connected (redesign B8)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adapters.connectors import ConnectorInfo, connect, disconnect, list_connections
from adapters.connectors.registry import NotConfiguredError, privacy_facts
from api.deps import needs, tenant_context
from core.tenancy import Role, TenantContext

router = APIRouter(tags=["connections"])


class ConnectionsView(BaseModel):
    connections: list[ConnectorInfo]
    connected_count: int
    total: int
    privacy: list[dict[str, str]]


@router.get("/connections", response_model=ConnectionsView)
async def connections(ctx: TenantContext = Depends(tenant_context)) -> ConnectionsView:
    found = await list_connections(ctx.tenant_id)
    return ConnectionsView(
        connections=found,
        connected_count=sum(1 for c in found if c.status == "connected"),
        total=len(found),
        privacy=privacy_facts(),
    )


@router.post("/connections/{category}/connect", response_model=ConnectorInfo)
async def connect_tool(
    category: str, ctx: TenantContext = Depends(needs(Role.admin))
) -> ConnectorInfo:
    """Connecting a tool decides what Plexus can read, so it needs an admin."""
    try:
        return await connect(ctx.tenant_id, category)
    except NotConfiguredError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/connections/{category}/disconnect", response_model=ConnectorInfo)
async def disconnect_tool(
    category: str, ctx: TenantContext = Depends(needs(Role.admin))
) -> ConnectorInfo:
    try:
        return await disconnect(ctx.tenant_id, category)
    except NotConfiguredError as exc:
        raise HTTPException(404, str(exc)) from exc
