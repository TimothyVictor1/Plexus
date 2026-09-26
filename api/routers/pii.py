"""Live PII boundary: tokenise text exactly as the adapters do."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import tenant_context
from core.pii.boundary import get_boundary, scan
from core.pii.vault import TokenVault
from core.tenancy import TenantContext

router = APIRouter(tags=["pii"])


class TokeniseRequest(BaseModel):
    text: str


@router.post("/pii/tokenise")
async def tokenise(
    body: TokeniseRequest, ctx: TenantContext = Depends(tenant_context)
) -> dict[str, Any]:
    boundary = get_boundary()
    tokenised, tmap = boundary.tokenize_text(body.text, tenant_id=ctx.tenant_id)
    found = [
        {
            "token": token,
            "entity_type": etype,
            "in_vault": await TokenVault().get(ctx.tenant_id, token) is not None,
        }
        for token, etype, _ in tmap.items_for_vault()
    ]
    return {
        "tokenised": tokenised,
        "found": found,
        "detected": len(found),
        "leaks": scan(tokenised, ctx.tenant_id),
    }
