"""Everything Home needs, in one call (redesign B9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import tenant_context
from core.db.pool import tenant_conn
from core.insights import Insight, top_insights
from core.org import OrgStatus, get_org, org_status
from core.review import ReviewItem, open_items
from core.tenancy import TenantContext

router = APIRouter(tags=["home"])


class ConnectedTool(BaseModel):
    category: str
    connected: bool


class Home(BaseModel):
    org_name: str = ""
    is_demo: bool = False
    status: OrgStatus
    open_reviews: list[ReviewItem] = Field(default_factory=list)
    open_review_count: int = 0
    insights: list[Insight] = Field(default_factory=list)
    tools: list[ConnectedTool] = Field(default_factory=list)


@router.get("/home", response_model=Home)
async def home(ctx: TenantContext = Depends(tenant_context)) -> Home:
    """One request, so the first screen does not arrive in pieces."""
    org = await get_org(ctx.tenant_id)
    status = await org_status(ctx.tenant_id)
    reviews = await open_items(ctx.tenant_id)

    async with tenant_conn(ctx.tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT category, status FROM connections WHERE tenant_id=$1 ORDER BY category",
            ctx.tenant_id,
        )

    return Home(
        org_name=org.display_name if org else "",
        is_demo=org.is_demo if org else False,
        status=status,
        open_reviews=reviews[:3],
        open_review_count=len(reviews),
        insights=await top_insights(ctx.tenant_id) if status.stage == "ready" else [],
        tools=[
            ConnectedTool(category=r["category"], connected=r["status"] == "connected")
            for r in rows
        ],
    )


@router.get("/insights", response_model=list[Insight])
async def insights(ctx: TenantContext = Depends(tenant_context)) -> list[Insight]:
    return await top_insights(ctx.tenant_id)
