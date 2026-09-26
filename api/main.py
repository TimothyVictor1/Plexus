"""Plexus API. Everything is versioned under /v1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agents.extract.ingest import load_all_gazetteers
from api.routers.actions import router as actions_router
from api.routers.health import router as health_router
from api.routers.org import router as org_router
from api.routers.overview import router as overview_router
from api.routers.pii import router as pii_router
from api.routers.processes import router as processes_router
from core.db.pool import close_pool

API_VERSION = "0.2.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The PII gazetteer lives in Postgres so every process tokenises identically.
    try:
        await load_all_gazetteers()
    except Exception as exc:  # the API must boot before the database is seeded
        print(f"gazetteer not loaded ({type(exc).__name__}); run make seed")
    yield
    await close_pool()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Plexus",
        version=API_VERSION,
        description="Organisational nervous system with earned autonomy.",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    routers = (
        health_router,
        org_router,
        processes_router,
        overview_router,
        pii_router,
        actions_router,
    )
    for r in routers:
        app.include_router(r, prefix="/v1")
    return app


app = create_app()
