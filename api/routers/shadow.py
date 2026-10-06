"""The shadow workforce's record: what agents would have done, and how often they were right."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import tenant_context
from core.shadow import service as shadow
from core.shadow.models import Scoreboard, ShadowRun
from core.tenancy import TenantContext

router = APIRouter(tags=["shadow"])


@router.get("/shadow", response_model=Scoreboard)
async def scoreboard(ctx: TenantContext = Depends(tenant_context)) -> Scoreboard:
    """What every shadowing agent has earned so far.

    Read-only, and so is everything behind it: a shadowing agent writes down what it would do
    and touches nothing. The record is the whole product — it is what turns "would you let AI
    do this" into a question with evidence behind it.
    """
    return await shadow.scoreboard(ctx.tenant_id)


@router.get("/shadow/{process_id}", response_model=list[ShadowRun])
async def runs(process_id: str, ctx: TenantContext = Depends(tenant_context)) -> list[ShadowRun]:
    """The individual predictions behind a score, so the number can be checked rather than
    believed."""
    return await shadow.runs_for(ctx.tenant_id, process_id)
