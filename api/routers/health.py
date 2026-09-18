"""Liveness and deep health endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from api.health import HealthReport, default_checks, run_checks
from core.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health", response_model=HealthReport)
async def health(request: Request, response: Response) -> HealthReport:
    checks = getattr(request.app.state, "health_checks", None) or default_checks(get_settings())
    report = await run_checks(checks)
    if report.status == "down":
        response.status_code = 503
    return report
