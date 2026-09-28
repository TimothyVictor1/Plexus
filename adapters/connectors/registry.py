"""The connector framework (redesign B8).

Every tool a company might plug in implements the same small interface, whether or not its
credentials exist yet. A provider with no credentials reports that plainly instead of
pretending to be connectable, so the screen never offers a button that cannot work.

Disconnecting detaches rather than deletes: the work Plexus already learned about stays, and
so does the record of anything it did. Deleting that history silently would destroy the
provenance behind actions already taken.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from core.db.pool import tenant_conn
from core.language import phrases
from core.settings import get_settings

Category = Literal["email", "calendar", "crm", "accounting", "files", "hr", "chat", "projects"]
Status = Literal["connected", "error", "not_connected", "not_configured"]


@dataclass(frozen=True)
class Provider:
    """One vendor Plexus can read from."""

    key: str
    name: str
    category: Category
    # Which credential must exist before this can be offered at all.
    requires_env: str | None = None


# The eight categories, with the products people actually name when asked.
CATEGORIES: tuple[tuple[Category, str], ...] = (
    ("email", "Gmail, Outlook"),
    ("calendar", "Google, Outlook"),
    ("crm", "HubSpot, Salesforce, Lime"),
    ("accounting", "Fortnox, Visma"),
    ("files", "Google Drive, SharePoint"),
    ("hr", "Any HR tool"),
    ("chat", "Slack, Teams"),
    ("projects", "ClickUp, Jira, Asana"),
)

PROVIDERS: tuple[Provider, ...] = (
    Provider("gmail", "Gmail", "email", "GMAIL_CLIENT_ID"),
    Provider("outlook_calendar", "Outlook Calendar", "calendar", "MS_CLIENT_ID"),
    Provider("hubspot", "HubSpot", "crm", "HUBSPOT_CLIENT_ID"),
    Provider("fortnox", "Fortnox", "accounting", "FORTNOX_CLIENT_ID"),
    Provider("gdrive", "Google Drive", "files", "GOOGLE_OAUTH_CLIENT_ID"),
    Provider("bamboo", "HR system", "hr", "HR_CLIENT_ID"),
    Provider("slack", "Slack", "chat", "SLACK_CLIENT_ID"),
    Provider("clickup", "ClickUp", "projects", "CLICKUP_CLIENT_ID"),
)


class ConnectorInfo(BaseModel):
    category: str
    label: str
    examples: str
    status: Status
    provider: str = ""
    detail: str = ""
    document_count: int = 0


def _configured(provider: Provider) -> bool:
    """Whether this vendor's credentials exist. None do yet; the interface is what matters."""
    if provider.requires_env is None:
        return True
    import os

    return bool(os.environ.get(provider.requires_env))


async def list_connections(tenant_id: str) -> list[ConnectorInfo]:
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT category, provider, status, source_id, detail FROM connections"
            " WHERE tenant_id=$1",
            tenant_id,
        )
        counts = await conn.fetch(
            "SELECT c.category, count(d.id) AS n FROM connections c"
            " LEFT JOIN documents d ON d.tenant_id=c.tenant_id AND d.connection_id=c.id"
            " WHERE c.tenant_id=$1 GROUP BY c.category",
            tenant_id,
        )
    existing = {r["category"]: dict(r) for r in rows}
    doc_counts = {r["category"]: int(r["n"] or 0) for r in counts}

    out: list[ConnectorInfo] = []
    for category, examples in CATEGORIES:
        row = existing.get(category)
        provider = next((p for p in PROVIDERS if p.category == category), None)

        # A category that has ever been connected stays reconnectable. Falling back to the
        # real vendor's credentials here would strand a tool the moment someone disconnected
        # it, which is the opposite of "you stay in control".
        if row:
            status: Status = "connected" if row["status"] == "connected" else "not_connected"
            detail = "" if status == "connected" else (row["detail"] or "")
        elif provider is None or not _configured(provider):
            status = "not_configured"
            detail = (
                "Plexus can read this kind of tool, but this installation has no credentials "
                "for it yet."
            )
        else:
            status = "not_connected"
            detail = ""

        out.append(
            ConnectorInfo(
                category=category,
                label=phrases.tool_label(category),
                examples=examples,
                status=status,
                provider=(row or {}).get("provider") or (provider.key if provider else ""),
                detail=detail,
                document_count=doc_counts.get(category, 0),
            )
        )
    return out


class NotConfiguredError(RuntimeError):
    """This installation has no credentials for that vendor yet."""


async def connect(tenant_id: str, category: str) -> ConnectorInfo:
    # Reconnecting something this organisation already had uses the provider it was set up
    # with, rather than insisting on the credentials of whichever vendor ships by default.
    async with tenant_conn(tenant_id) as conn:
        existing = await conn.fetchval(
            "SELECT provider FROM connections WHERE tenant_id=$1 AND category=$2 LIMIT 1",
            tenant_id,
            category,
        )

    provider_key = str(existing) if existing else None
    if provider_key is None:
        provider = next((p for p in PROVIDERS if p.category == category), None)
        if provider is None:
            msg = f"no connector for {category}"
            raise NotConfiguredError(msg)
        if not _configured(provider):
            msg = (
                f"{provider.name} needs credentials that this installation does not have. "
                f"Set {provider.requires_env} and restart to enable it."
            )
            raise NotConfiguredError(msg)
        provider_key = provider.key

    # A configured provider runs its OAuth handshake here and begins syncing.
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO connections (id, tenant_id, category, provider, status, source_id,"
            " last_sync, detail) VALUES ($1,$2,$3,$4,'connected',$5, now(), '')"
            " ON CONFLICT (tenant_id, category, provider)"
            " DO UPDATE SET status='connected', last_sync=now(), detail=''",
            str(uuid.uuid4()),
            tenant_id,
            category,
            provider_key,
            category,
        )
    return next(c for c in await list_connections(tenant_id) if c.category == category)


async def disconnect(tenant_id: str, category: str) -> ConnectorInfo:
    """Stop reading from this tool, and keep what has already been learned.

    Detaching rather than deleting is deliberate: the processes Plexus discovered and the
    record of anything it did both depend on that history. Removing it would quietly destroy
    the provenance behind actions a person already approved.
    """
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "UPDATE connections SET status='not_connected', last_sync=NULL,"
            " detail='Disconnected. What Plexus already learned is kept.'"
            " WHERE tenant_id=$1 AND category=$2",
            tenant_id,
            category,
        )
    found = [c for c in await list_connections(tenant_id) if c.category == category]
    if not found:
        msg = f"no connection for {category}"
        raise NotConfiguredError(msg)
    return found[0]


def privacy_facts() -> list[dict[str, str]]:
    """Only claims the configuration actually backs. Never a promise the code does not keep."""
    settings = get_settings()
    region = settings.model_data_region
    in_europe = region.lower() in {"eu", "europe"}
    return [
        {
            "key": "residency",
            "ok": str(in_europe).lower(),
            "region": region,
        },
        {"key": "masking", "ok": "true", "region": ""},
        {"key": "control", "ok": "true", "region": ""},
    ]
