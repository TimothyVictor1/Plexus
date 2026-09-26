"""The model router (spec 09).

Every model call in Plexus goes through here. The router owns role-to-vendor binding, the
production vendor-separation check, cost accounting, and tracing. No module outside
core/models/providers imports a vendor SDK.
"""

from __future__ import annotations

import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, cast

import yaml
from pydantic import BaseModel

from core.db.pool import tenant_conn
from core.models.providers.google import GoogleProvider
from core.models.providers.local import LocalProvider
from core.models.types import (
    Completion,
    Message,
    ModelId,
    Role,
    VendorSeparationError,
)
from core.settings import Env, Settings, get_settings

CONFIG_PATH = Path("config/models.yaml")
PRICES_PATH = Path("config/model_prices.yaml")


def _prices(vendor: str, model: str) -> tuple[float, float]:
    """Per-million-token prices. Zero until a real rate is configured."""
    try:
        table = yaml.safe_load(PRICES_PATH.read_text(encoding="utf-8")) or {}
    except OSError:
        return 0.0, 0.0
    entry = (table.get(vendor) or {}).get(model) or (table.get(vendor) or {}).get("*") or {}
    return float(entry.get("input", 0.0)), float(entry.get("output", 0.0))


class RoleConfig(BaseModel):
    vendor: str
    model: str
    effort: str | None = None


class Provider(Protocol):
    vendor: str

    async def complete(
        self,
        messages: list[Message],
        *,
        role: str,
        context: dict[str, Any] | None = None,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 4096,
    ) -> Completion: ...
    async def list_models(self) -> list[str]: ...


class Router:
    def __init__(self, roles: dict[Role, RoleConfig], separation: str, env: Env) -> None:
        self.roles = roles
        self.separation = separation
        self.env = env
        self._providers: dict[str, Provider] = {}

    @classmethod
    def from_config(cls, path: Path = CONFIG_PATH, settings: Settings | None = None) -> Router:
        s = settings or get_settings()
        raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        profile_name = s.plexus_model_profile
        roles_raw: dict[str, Any] = dict(raw.get("roles", {}))
        separation = str(raw.get("separation", "vendor"))
        if profile_name and profile_name != "default":
            profile = raw.get("profiles", {}).get(profile_name)
            if profile is None:
                msg = f"unknown model profile {profile_name!r}"
                raise ValueError(msg)
            separation = str(profile.get("separation", separation))
            roles_raw.update({k: v for k, v in profile.items() if k != "separation"})

        roles = {Role(k): RoleConfig(**v) for k, v in roles_raw.items() if k in set(Role)}
        router = cls(roles, separation, s.plexus_env)
        router._check_separation()
        return router

    def _check_separation(self) -> None:
        actor, verifier = self.roles.get(Role.actor), self.roles.get(Role.verifier)
        if actor is None or verifier is None:
            return
        same_vendor = actor.vendor == verifier.vendor
        same_model = actor.model == verifier.model
        clash = same_model if self.separation == "model" else same_vendor
        if not clash:
            return
        detail = (
            f"actor={actor.vendor}/{actor.model} verifier={verifier.vendor}/{verifier.model} "
            f"separation={self.separation}"
        )
        if self.env is Env.production:
            raise VendorSeparationError(
                "actor and verifier must be separated in production: " + detail
            )
        # Outside production this is a loud warning, not a boot failure, so a laptop can run
        # the local profile end to end.
        self.separation_warning = detail

    separation_warning: str | None = None

    def provider_for(self, role: Role) -> Provider:
        cfg = self.roles[role]
        key = f"{cfg.vendor}:{cfg.model}"
        if key in self._providers:
            return self._providers[key]

        settings = get_settings()
        if cfg.vendor == "google":
            price_in, price_out = _prices(cfg.vendor, cfg.model)
            provider: Provider = GoogleProvider(
                cfg.model, settings.google_api_key, price_in=price_in, price_out=price_out
            )
        elif cfg.vendor == "local":
            provider = LocalProvider(cfg.model)
        else:
            msg = (
                f"role {role.value} is configured for vendor {cfg.vendor!r}, which has no "
                "provider. Add one under core/models/providers, or change config/models.yaml."
            )
            raise ValueError(msg)

        self._providers[key] = provider
        return provider

    def available(self, role: Role) -> bool:
        """Whether this role can actually reach its vendor right now."""
        provider = self.provider_for(role)
        return bool(getattr(provider, "available", True))

    def model_id(self, role: Role) -> ModelId:
        cfg = self.roles[role]
        return ModelId(vendor=cfg.vendor, model=cfg.model)

    async def complete(
        self,
        role: Role,
        messages: list[Message],
        *,
        tenant_id: str,
        context: dict[str, Any] | None = None,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 4096,
        trace_id: str = "",
    ) -> Completion:
        provider = self.provider_for(role)
        completion = await provider.complete(
            messages, role=role.value, context=context, schema=schema, max_tokens=max_tokens
        )
        completion.model = self.model_id(role)
        await self._record_cost(tenant_id, role, completion, trace_id)
        return completion

    async def _record_cost(
        self, tenant_id: str, role: Role, completion: Completion, trace_id: str
    ) -> None:
        try:
            async with tenant_conn(tenant_id) as conn:
                await conn.execute(
                    "INSERT INTO model_calls (id, tenant_id, role, vendor, model,"
                    " input_tokens, output_tokens, cost_usd, latency_ms, ok, trace_id)"
                    " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,true,$10)",
                    str(uuid.uuid4()),
                    tenant_id,
                    role.value,
                    completion.model.vendor,
                    completion.model.model,
                    completion.usage.input_tokens,
                    completion.usage.output_tokens,
                    completion.usage.cost_usd,
                    completion.latency_ms,
                    trace_id,
                )
        except Exception:
            return


@lru_cache(maxsize=1)
def get_router() -> Router:
    return Router.from_config()


def render(messages: list[tuple[str, str]]) -> list[Message]:
    return [Message(role=cast(Any, r), content=c) for r, c in messages]


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, default=str)
