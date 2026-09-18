"""Plexus API. Everything is versioned under /v1."""

from __future__ import annotations

from fastapi import FastAPI

from api.routers.health import router as health_router

API_VERSION = "0.0.1"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Plexus",
        version=API_VERSION,
        description="Organisational nervous system with earned autonomy.",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
    )
    app.include_router(health_router, prefix="/v1")
    return app


app = create_app()
