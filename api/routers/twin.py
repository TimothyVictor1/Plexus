"""The digital twin: a live model of how work moves, and what would happen if it changed."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import tenant_context
from core.processes import get_process
from core.tenancy import TenantContext
from twin.financial import FinancialTwin
from twin.financial import build as build_financial
from twin.general import GeneralTwin
from twin.general import build as build_general
from twin.kinds import KINDS, TwinKind
from twin.lenses import LENSES, LensOption, LensView, view
from twin.organisation import (
    OrgModel,
    Scenario,
    build_model,
    demand_changes,
    person_leaves,
    process_changes,
)
from twin.people import PeopleTwin, PersonTwin, successor_brief
from twin.people import build as build_people

router = APIRouter(tags=["twin"])


class Answer(BaseModel):
    """A scenario and the chosen reading of it.

    The scenario is the same whichever lens is asked for: the arithmetic over what happened
    does not change because of who is reading it. Only the second half does.
    """

    scenario: Scenario
    lens: LensView


class WhatIf(BaseModel):
    kind: Literal["person_leaves", "demand_changes", "process_changes"]
    # Which reading of the answer to return alongside the operational one. Defaults to the
    # operational reading, so a caller that knows nothing about lenses behaves as before.
    lens: Literal["operations", "cash", "people", "risk"] = "operations"
    person: str | None = None
    process_id: str | None = None
    multiplier: float = Field(default=2.0, ge=0.1, le=10.0)
    remove_step: str | None = None
    speed_up_percent: float = Field(default=0.0, ge=0.0, le=95.0)


@router.get("/twin", response_model=OrgModel)
async def twin(ctx: TenantContext = Depends(tenant_context)) -> OrgModel:
    """The model itself: who does what, how much, and where that is fragile."""
    return await build_model(ctx.tenant_id)


@router.get("/twins", response_model=list[TwinKind])
async def twins() -> list[TwinKind]:
    """Every view of the company a person can choose between."""
    return KINDS


@router.get("/twins/general", response_model=GeneralTwin)
async def general(ctx: TenantContext = Depends(tenant_context)) -> GeneralTwin:
    """All the twins side by side, each saying whether it can be built from what is connected."""
    return build_general(await build_model(ctx.tenant_id))


@router.get("/twins/financial", response_model=FinancialTwin)
async def financial(ctx: TenantContext = Depends(tenant_context)) -> FinancialTwin:
    """Where money sits, in the currencies the records actually carry."""
    return build_financial(await build_model(ctx.tenant_id))


@router.get("/twins/people", response_model=PeopleTwin)
async def people(ctx: TenantContext = Depends(tenant_context)) -> PeopleTwin:
    """What each person does, and what would not survive their leaving."""
    return build_people(await build_model(ctx.tenant_id))


class Brief(BaseModel):
    """What to tell whoever takes this work over, in the order it will come up."""

    person: str
    lines: list[str]


@router.get("/twins/people/{token}/handover", response_model=Brief)
async def handover(token: str, ctx: TenantContext = Depends(tenant_context)) -> Brief:
    twin = await person(token, ctx)
    return Brief(person=twin.label, lines=successor_brief(twin))


@router.get("/twins/people/{token}", response_model=PersonTwin)
async def person(token: str, ctx: TenantContext = Depends(tenant_context)) -> PersonTwin:
    """One person's twin: what they do, and the handover if they go."""
    twin = build_people(await build_model(ctx.tenant_id))
    for candidate in twin.people:
        if candidate.token == token or candidate.label == token:
            return candidate
    raise HTTPException(404, "nobody by that name shows up in the recent record")


@router.get("/twin/lenses", response_model=list[LensOption])
async def lenses() -> list[LensOption]:
    """The readings a person can choose between before running a scenario."""
    return LENSES


@router.post("/twin/what-if", response_model=Answer)
async def what_if(body: WhatIf, ctx: TenantContext = Depends(tenant_context)) -> Answer:
    """Try a change against the model before making it for real.

    Nothing here touches the live graph or any customer system. It is arithmetic over what
    already happened, which is why every answer carries the assumptions it rests on.
    """
    model = await build_model(ctx.tenant_id)
    scenario = await _run(model, body, ctx.tenant_id)
    return Answer(scenario=scenario, lens=view(model, scenario, body.lens))


async def _run(model: OrgModel, body: WhatIf, tenant_id: str) -> Scenario:
    if body.kind == "person_leaves":
        if not body.person:
            raise HTTPException(400, "say which person")
        return person_leaves(model, body.person)

    if not body.process_id:
        raise HTTPException(400, "say which way of working")

    if body.kind == "demand_changes":
        return demand_changes(model, body.process_id, body.multiplier)

    detail = await get_process(tenant_id, body.process_id)
    if detail is None:
        raise HTTPException(404, "no such way of working")
    waits = [(w.from_step, w.to_step, w.duration.seconds) for w in detail.waits]
    return process_changes(model, body.process_id, waits, body.remove_step, body.speed_up_percent)
