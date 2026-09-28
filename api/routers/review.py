"""Things waiting for a person (redesign B5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import needs, tenant_context
from core.review import Decision, ReviewItem, approve, done_today, open_items, skip
from core.tenancy import Role, TenantContext

router = APIRouter(tags=["review"])


class ReviewList(BaseModel):
    open: list[ReviewItem]
    done_today: list[ReviewItem]


class ApproveRequest(BaseModel):
    edited_text: str | None = Field(default=None, max_length=8000)


@router.get("/review", response_model=ReviewList)
async def review(ctx: TenantContext = Depends(tenant_context)) -> ReviewList:
    return ReviewList(
        open=await open_items(ctx.tenant_id),
        done_today=await done_today(ctx.tenant_id),
    )


@router.post("/review/{item_id}/approve", response_model=Decision)
async def approve_item(
    item_id: str,
    body: ApproveRequest | None = None,
    ctx: TenantContext = Depends(needs(Role.approver)),
) -> Decision:
    """Saying yes. The write still goes through the executor, so every check applies."""
    try:
        return await approve(
            ctx.tenant_id, item_id, ctx.subject, (body.edited_text if body else None)
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/review/{item_id}/skip", response_model=Decision)
async def skip_item(item_id: str, ctx: TenantContext = Depends(needs(Role.approver))) -> Decision:
    try:
        return await skip(ctx.tenant_id, item_id, ctx.subject)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
