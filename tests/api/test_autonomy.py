"""Changing how much Plexus does, and the rules that stop it (redesign B4)."""

from __future__ import annotations

import pytest

from core.db.pool import tenant_conn
from core.ledger import ledger
from core.ledger.models import Actor, NewLedgerEntry, Tier
from core.processes import autonomy, get_process

pytestmark = pytest.mark.integration

TENANT = "demo"
PROCESS = "monthly_reporting"


async def _reset(tier: Tier = Tier.OBSERVE, paused: bool = False) -> None:
    async with tenant_conn(TENANT) as conn:
        await conn.execute(
            "INSERT INTO process_state (tenant_id, process_id, tier, paused)"
            " VALUES ($1,$2,$3,$4) ON CONFLICT (tenant_id, process_id)"
            " DO UPDATE SET tier=EXCLUDED.tier, paused=EXCLUDED.paused",
            TENANT,
            PROCESS,
            tier.name,
            paused,
        )


async def _earn(n: int) -> None:
    """Give the process a real record of approvals so it can qualify."""
    for _ in range(n):
        await ledger.append(
            NewLedgerEntry(
                tenant_id=TENANT,
                process_id=PROCESS,
                entry_type="approval",
                actor=Actor(kind="human", id="tester", role="approver"),
                payload={},
            )
        )


async def test_promotion_is_refused_with_a_reason_a_person_can_act_on() -> None:
    await _reset()
    outcome = await autonomy.promote(TENANT, PROCESS, "tester", "admin")
    assert outcome.ok is False
    assert outcome.reason
    assert "decisions" in outcome.reason


async def test_promotion_succeeds_once_the_record_justifies_it() -> None:
    await _reset()
    await _earn(30)
    outcome = await autonomy.promote(TENANT, PROCESS, "tester", "admin")
    assert outcome.ok is True
    assert outcome.to_level == outcome.from_level + 1
    detail = await get_process(TENANT, PROCESS)
    assert detail is not None
    assert detail.autonomy.level == outcome.to_level


async def test_a_paused_process_cannot_be_promoted() -> None:
    await _reset(paused=True)
    await _earn(30)
    outcome = await autonomy.promote(TENANT, PROCESS, "tester", "admin")
    assert outcome.ok is False
    assert "paused" in outcome.reason.lower()
    await _reset()


async def test_pulling_back_never_has_to_be_earned() -> None:
    await _reset(Tier.SUGGEST)
    outcome = await autonomy.demote(TENANT, PROCESS, "tester", "admin")
    assert outcome.ok is True
    assert outcome.to_level == 2


async def test_the_bottom_and_top_rungs_hold() -> None:
    await _reset(Tier.OBSERVE)
    assert (await autonomy.demote(TENANT, PROCESS, "t", "admin")).ok is False
    await _reset(Tier.AUTONOMOUS)
    assert (await autonomy.promote(TENANT, PROCESS, "t", "admin")).ok is False
    await _reset()


async def test_pause_and_resume_round_trip() -> None:
    await _reset()
    assert (await autonomy.set_paused(TENANT, PROCESS, True, "t", "approver")).ok is True
    detail = await get_process(TENANT, PROCESS)
    assert detail is not None and detail.paused is True

    assert (await autonomy.set_paused(TENANT, PROCESS, True, "t", "approver")).ok is False
    assert (await autonomy.set_paused(TENANT, PROCESS, False, "t", "approver")).ok is True
    detail = await get_process(TENANT, PROCESS)
    assert detail is not None and detail.paused is False


async def test_every_change_is_written_to_the_ledger() -> None:
    await _reset(Tier.SUGGEST)
    before = len(await ledger.entries(TENANT, PROCESS, entry_type="demotion", limit=200))
    await autonomy.demote(TENANT, PROCESS, "auditor", "admin")
    after = await ledger.entries(TENANT, PROCESS, entry_type="demotion", limit=200)
    assert len(after) == before + 1
    entry = after[0]
    assert entry.actor["id"] == "auditor"
    assert entry.payload["from"] and entry.payload["to"]
    assert entry.ts is not None
    await _reset()


async def test_an_unknown_process_is_not_silently_created() -> None:
    with pytest.raises(autonomy.ProcessNotFoundError):
        await autonomy.promote(TENANT, "no-such-process", "t", "admin")
