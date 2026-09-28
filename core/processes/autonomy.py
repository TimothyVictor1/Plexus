"""Changing how much Plexus is allowed to do (redesign B4).

Every rule is enforced here, on the server. The screen only ever hides a button; it never
decides. A refusal comes back as a sentence a person can act on, not an error code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from core.db.pool import tenant_conn
from core.ledger import ledger
from core.ledger.models import Actor, EntryType, NewLedgerEntry, Tier
from core.ledger.trust import compute_trust, load_config, next_transition

Direction = Literal["promote", "demote"]


@dataclass
class Outcome:
    ok: bool
    from_level: int
    to_level: int
    reason: str


class ProcessNotFoundError(LookupError):
    """No such way of working in this organisation."""


async def _state(tenant_id: str, process_id: str) -> tuple[Tier, bool]:
    async with tenant_conn(tenant_id) as conn:
        row = await conn.fetchrow(
            "SELECT s.tier, s.paused FROM processes p"
            " LEFT JOIN process_state s ON s.tenant_id=p.tenant_id AND s.process_id=p.id"
            " WHERE p.tenant_id=$1 AND p.id=$2",
            tenant_id,
            process_id,
        )
    if row is None:
        raise ProcessNotFoundError(process_id)
    return Tier.parse(row["tier"] or "OBSERVE"), bool(row["paused"])


async def _write_tier(tenant_id: str, process_id: str, tier: Tier) -> None:
    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO process_state (tenant_id, process_id, tier) VALUES ($1,$2,$3)"
            " ON CONFLICT (tenant_id, process_id) DO UPDATE SET tier=EXCLUDED.tier,"
            " updated_at=now()",
            tenant_id,
            process_id,
            tier.name,
        )


async def _record(
    tenant_id: str,
    process_id: str,
    entry_type: str,
    subject: str,
    role: str,
    payload: dict[str, object],
) -> None:
    await ledger.append(
        NewLedgerEntry(
            tenant_id=tenant_id,
            process_id=process_id,
            entry_type=cast(EntryType, entry_type),
            actor=Actor(kind="human", id=subject, role=role),
            payload=payload,
        )
    )


async def promote(tenant_id: str, process_id: str, subject: str, role: str) -> Outcome:
    """Move one rung up, but only if the process has earned it."""
    tier, paused = await _state(tenant_id, process_id)
    cfg = load_config()

    if tier >= Tier.AUTONOMOUS:
        return Outcome(
            False, int(tier) + 1, int(tier) + 1, "Plexus already does everything it can here."
        )
    if paused:
        return Outcome(
            False,
            int(tier) + 1,
            int(tier) + 1,
            "This is paused. Resume it before letting Plexus do more.",
        )

    entries = await ledger.entries(tenant_id, process_id, limit=cfg.window_n)
    breakdown = compute_trust(list(reversed(entries)), cfg)
    transition = next_transition(tier, breakdown, cfg)

    if not transition.eligible:
        return Outcome(False, int(tier) + 1, int(tier) + 1, transition.reason)

    target = Tier(int(tier) + 1)
    await _write_tier(tenant_id, process_id, target)
    await _record(
        tenant_id,
        process_id,
        "promotion",
        subject,
        role,
        {
            "from": tier.name,
            "to": target.name,
            "trust": round(breakdown.trust, 3),
            "decisions": breakdown.samples,
            "reason": "approved by a person",
        },
    )
    return Outcome(True, int(tier) + 1, int(target) + 1, "")


async def demote(tenant_id: str, process_id: str, subject: str, role: str) -> Outcome:
    """Move one rung down. Always allowed: pulling back never needs to be earned."""
    tier, _ = await _state(tenant_id, process_id)
    if tier <= Tier.OBSERVE:
        return Outcome(False, 1, 1, "Plexus already does as little as it can here.")

    target = Tier(int(tier) - 1)
    await _write_tier(tenant_id, process_id, target)
    await _record(
        tenant_id,
        process_id,
        "demotion",
        subject,
        role,
        {"from": tier.name, "to": target.name, "reason": "asked for by a person"},
    )
    return Outcome(True, int(tier) + 1, int(target) + 1, "")


async def set_paused(
    tenant_id: str, process_id: str, paused: bool, subject: str, role: str
) -> Outcome:
    """Pause or resume. The executor checks this flag before every single action."""
    tier, already = await _state(tenant_id, process_id)
    level = int(tier) + 1
    if already == paused:
        return Outcome(
            False,
            level,
            level,
            "This is already paused." if paused else "This is already running.",
        )

    async with tenant_conn(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO process_state (tenant_id, process_id, tier, paused)"
            " VALUES ($1,$2,$3,$4) ON CONFLICT (tenant_id, process_id)"
            " DO UPDATE SET paused=EXCLUDED.paused, updated_at=now()",
            tenant_id,
            process_id,
            tier.name,
            paused,
        )
    await _record(
        tenant_id,
        process_id,
        "pause" if paused else "unpause",
        subject,
        role,
        {"level": level},
    )
    return Outcome(True, level, level, "")
