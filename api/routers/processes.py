"""Ways of working: the list, one in detail, and renaming (redesign B3)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import needs, tenant_context
from core.language import set_override
from core.processes import ProcessDetail, ProcessSummary, autonomy, get_process, list_processes
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


class ChangeResult(BaseModel):
    ok: bool
    from_level: int
    to_level: int
    reason: str
    process: ProcessDetail


async def _result(tenant_id: str, process_id: str, outcome: autonomy.Outcome) -> ChangeResult:
    detail = await get_process(tenant_id, process_id)
    if detail is None:  # pragma: no cover - the change proved it exists
        raise HTTPException(404, "no such way of working")
    return ChangeResult(
        ok=outcome.ok,
        from_level=outcome.from_level,
        to_level=outcome.to_level,
        reason=outcome.reason,
        process=detail,
    )


@router.post("/processes/{process_id}/promote", response_model=ChangeResult)
async def promote(process_id: str, ctx: TenantContext = Depends(needs(Role.admin))) -> ChangeResult:
    """Letting Plexus do more changes what it can touch, so it needs an admin."""
    try:
        outcome = await autonomy.promote(ctx.tenant_id, process_id, ctx.subject, "admin")
    except autonomy.ProcessNotFoundError as exc:
        raise HTTPException(404, "no such way of working") from exc
    return await _result(ctx.tenant_id, process_id, outcome)


@router.post("/processes/{process_id}/demote", response_model=ChangeResult)
async def demote(process_id: str, ctx: TenantContext = Depends(needs(Role.admin))) -> ChangeResult:
    try:
        outcome = await autonomy.demote(ctx.tenant_id, process_id, ctx.subject, "admin")
    except autonomy.ProcessNotFoundError as exc:
        raise HTTPException(404, "no such way of working") from exc
    return await _result(ctx.tenant_id, process_id, outcome)


@router.post("/processes/{process_id}/pause", response_model=ChangeResult)
async def pause(
    process_id: str, ctx: TenantContext = Depends(needs(Role.approver))
) -> ChangeResult:
    """Stopping Plexus is a safety control, so it sits one rung lower than promoting."""
    try:
        outcome = await autonomy.set_paused(
            ctx.tenant_id, process_id, True, ctx.subject, "approver"
        )
    except autonomy.ProcessNotFoundError as exc:
        raise HTTPException(404, "no such way of working") from exc
    return await _result(ctx.tenant_id, process_id, outcome)


@router.post("/processes/{process_id}/resume", response_model=ChangeResult)
async def resume(
    process_id: str, ctx: TenantContext = Depends(needs(Role.approver))
) -> ChangeResult:
    try:
        outcome = await autonomy.set_paused(
            ctx.tenant_id, process_id, False, ctx.subject, "approver"
        )
    except autonomy.ProcessNotFoundError as exc:
        raise HTTPException(404, "no such way of working") from exc
    return await _result(ctx.tenant_id, process_id, outcome)
