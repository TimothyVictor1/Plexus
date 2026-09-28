"""The digital twin: a live model of how work moves, and what would happen if it changed."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import tenant_context
from core.processes import get_process
from core.tenancy import TenantContext
from twin.organisation import (
    OrgModel,
    Scenario,
    build_model,
    demand_changes,
    person_leaves,
    process_changes,
)

router = APIRouter(tags=["twin"])


class WhatIf(BaseModel):
    kind: Literal["person_leaves", "demand_changes", "process_changes"]
    person: str | None = None
    process_id: str | None = None
    multiplier: float = Field(default=2.0, ge=0.1, le=10.0)
    remove_step: str | None = None
    speed_up_percent: float = Field(default=0.0, ge=0.0, le=95.0)


@router.get("/twin", response_model=OrgModel)
async def twin(ctx: TenantContext = Depends(tenant_context)) -> OrgModel:
    """The model itself: who does what, how much, and where that is fragile."""
    return await build_model(ctx.tenant_id)


@router.post("/twin/what-if", response_model=Scenario)
async def what_if(body: WhatIf, ctx: TenantContext = Depends(tenant_context)) -> Scenario:
    """Try a change against the model before making it for real.

    Nothing here touches the live graph or any customer system. It is arithmetic over what
    already happened, which is why every answer carries the assumptions it rests on.
    """
    model = await build_model(ctx.tenant_id)

    if body.kind == "person_leaves":
        if not body.person:
            raise HTTPException(400, "say which person")
        return person_leaves(model, body.person)

    if not body.process_id:
        raise HTTPException(400, "say which way of working")

    if body.kind == "demand_changes":
        return demand_changes(model, body.process_id, body.multiplier)

    detail = await get_process(ctx.tenant_id, body.process_id)
    if detail is None:
        raise HTTPException(404, "no such way of working")
    waits = [(w.from_step, w.to_step, w.duration.seconds) for w in detail.waits]
    return process_changes(model, body.process_id, waits, body.remove_step, body.speed_up_percent)
