"""Ways of working: the list, one in detail, and renaming (redesign B3)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import needs, tenant_context
from core.language import set_override
from core.processes import ProcessDetail, ProcessSummary, get_process, list_processes
from core.tenancy import Role, TenantContext

router = APIRouter(tags=["processes"])


class ProcessList(BaseModel):
    processes: list[ProcessSummary]


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/processes", response_model=ProcessList)
async def processes(
    filter: Literal["all", "slow"] = Query(default="all"),
    ctx: TenantContext = Depends(tenant_context),
) -> ProcessList:
    found = await list_processes(ctx.tenant_id, only_slow=filter == "slow")
    return ProcessList(processes=found)


@router.get("/processes/{process_id}", response_model=ProcessDetail)
async def process_detail(
    process_id: str, ctx: TenantContext = Depends(tenant_context)
) -> ProcessDetail:
    found = await get_process(ctx.tenant_id, process_id)
    if found is None:
        raise HTTPException(404, "no such way of working")
    return found


@router.patch("/processes/{process_id}", response_model=ProcessDetail)
async def rename(
    process_id: str,
    body: RenameRequest,
    ctx: TenantContext = Depends(needs(Role.operator)),
) -> ProcessDetail:
    """A person correcting the wording. Their name wins over anything generated."""
    if await get_process(ctx.tenant_id, process_id, allow_model=False) is None:
        raise HTTPException(404, "no such way of working")
    await set_override(ctx.tenant_id, process_id, body.name, ctx.subject)
    found = await get_process(ctx.tenant_id, process_id)
    if found is None:  # pragma: no cover - checked above
        raise HTTPException(404, "no such way of working")
    return found
