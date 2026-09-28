"""Inviting a colleague (redesign, Invite team).

An invite is a signed link with a role attached. Sending it by email needs an SMTP server
this installation does not have, so the link is handed back to whoever created it to pass on.
That is a real, working invite either way; only the delivery is manual.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

from pydantic import BaseModel, EmailStr

from core.db.pool import tenant_conn

InviteStatus = Literal["pending", "accepted", "revoked", "expired"]
VALID_FOR = timedelta(days=14)


class Invite(BaseModel):
    id: str
    email: str
    role: str
    status: InviteStatus
    invited_by: str
    created_at: datetime
    expires_at: datetime
    link: str = ""
    delivered: bool = False


class NewInvite(BaseModel):
    email: EmailStr
    role: Literal["viewer", "operator", "approver", "admin"] = "viewer"


class InviteError(ValueError):
    """The invite could not be created as asked."""


def _link(base_url: str, token: str) -> str:
    return f"{base_url.rstrip('/')}/join/{token}"


def _row_to_invite(row: Mapping[str, Any], base_url: str) -> Invite:
    return Invite(
        id=str(row["id"]),
        email=str(row["email"]),
        role=str(row["role"]),
        status=cast(InviteStatus, row["status"]),
        invited_by=str(row["invited_by"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        link=_link(base_url, str(row["token"])),
        delivered=False,
    )


async def create_invite(tenant_id: str, new: NewInvite, invited_by: str, base_url: str) -> Invite:
    token = secrets.token_urlsafe(24)
    now = datetime.now(tz=UTC)
    async with tenant_conn(tenant_id) as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM invites WHERE tenant_id=$1 AND lower(email)=lower($2)"
            " AND status='pending'",
            tenant_id,
            str(new.email),
        )
        if existing is not None:
            msg = f"{new.email} has already been invited and has not joined yet."
            raise InviteError(msg)

        row = await conn.fetchrow(
            "INSERT INTO invites (id, tenant_id, email, role, token, invited_by, expires_at)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *",
            str(uuid.uuid4()),
            tenant_id,
            str(new.email),
            new.role,
            token,
            invited_by,
            now + VALID_FOR,
        )
    return _row_to_invite(dict(row), base_url)


async def list_invites(tenant_id: str, base_url: str) -> list[Invite]:
    now = datetime.now(tz=UTC)
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "UPDATE invites SET status='expired'"
            " WHERE tenant_id=$1 AND status='pending' AND expires_at < $2",
            tenant_id,
            now,
        )
        rows = await conn.fetch(
            "SELECT * FROM invites WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 50",
            tenant_id,
        )
    return [_row_to_invite(dict(r), base_url) for r in rows]


async def revoke_invite(tenant_id: str, invite_id: str) -> bool:
    async with tenant_conn(tenant_id) as conn:
        result = await conn.execute(
            "UPDATE invites SET status='revoked' WHERE tenant_id=$1 AND id=$2 AND status='pending'",
            tenant_id,
            invite_id,
        )
    return str(result).endswith("1")
