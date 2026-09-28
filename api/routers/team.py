"""Inviting colleagues."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.deps import needs
from core.team import Invite, create_invite, list_invites, revoke_invite
from core.team.invites import InviteError, NewInvite
from core.tenancy import Role, TenantContext

router = APIRouter(tags=["team"])


class InviteList(BaseModel):
    invites: list[Invite]
    # No mail server is configured, so the link is handed back to be passed on by hand.
    delivery: str = "link"


def _base_url(request: Request) -> str:
    origin = request.headers.get("origin")
    return origin or "http://localhost:3000"


@router.get("/invites", response_model=InviteList)
async def invites(request: Request, ctx: TenantContext = Depends(needs(Role.admin))) -> InviteList:
    return InviteList(invites=await list_invites(ctx.tenant_id, _base_url(request)))


@router.post("/invites", response_model=Invite)
async def invite(
    body: NewInvite, request: Request, ctx: TenantContext = Depends(needs(Role.admin))
) -> Invite:
    """Deciding who can see a company's work is an admin's call."""
    try:
        return await create_invite(ctx.tenant_id, body, ctx.subject, _base_url(request))
    except InviteError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/invites/{invite_id}/revoke")
async def revoke(
    invite_id: str, ctx: TenantContext = Depends(needs(Role.admin))
) -> dict[str, bool]:
    if not await revoke_invite(ctx.tenant_id, invite_id):
        raise HTTPException(404, "no invite waiting with that id")
    return {"revoked": True}
