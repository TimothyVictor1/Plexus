"""The action pipeline against the real stack (spec 05, AT-05-3/4/5; spec 04, AT-04-2/3/4).

Never mock the safety path (working method §5): these exercise the real executor, the real
verifier gate, the real PII vault and the real pause flag.

    make up && make seed && PLEXUS_INTEGRATION=1 uv run pytest -m integration
"""

from __future__ import annotations

import pytest

from adapters.fixture.adapter import get_adapter
from core.action import executor
from core.action.models import HumanApproval
from core.action.pipeline import propose, run
from core.db.pool import tenant_conn
from core.ledger import ledger
from core.ledger.models import Tier

pytestmark = pytest.mark.integration

TENANT = "nordvik"
APPROVER = HumanApproval(subject="test-approver", role="approver")


async def _writes() -> int:
    async with tenant_conn(TENANT) as conn:
        return int(
            await conn.fetchval("SELECT count(*) FROM adapter_records WHERE tenant_id=$1", TENANT)
            or 0
        )


async def _set_paused(paused: bool, process_id: str | None = None) -> None:
    async with tenant_conn(TENANT) as conn:
        if process_id:
            await conn.execute(
                "UPDATE process_state SET paused=$3 WHERE tenant_id=$1 AND process_id=$2",
                TENANT,
                process_id,
                paused,
            )
        else:
            await conn.execute("UPDATE tenants SET paused=$2 WHERE id=$1", TENANT, paused)


# ---------------------------------------------------------------- tier gate
@pytest.mark.parametrize("tier", ["OBSERVE", "EXPLAIN", "SUGGEST"])
async def test_low_tiers_never_write(tier: str) -> None:
    before = await _writes()
    result = await run(TENANT, "proc-quote", tier_override=tier)
    assert result["outcome"]["outcome"] == "held"
    assert await _writes() == before, f"{tier} wrote to an adapter"


async def test_act_with_approval_needs_a_person() -> None:
    before = await _writes()
    result = await run(TENANT, "proc-quote", tier_override="ACT_WITH_APPROVAL")
    assert result["outcome"]["outcome"] == "held"
    assert "approver" in result["outcome"]["title"].lower()
    assert await _writes() == before


async def test_act_with_approval_executes_once_approved() -> None:
    before = await _writes()
    result = await run(TENANT, "proc-quote", tier_override="ACT_WITH_APPROVAL", approval=APPROVER)
    assert result["outcome"]["outcome"] == "executed"
    assert await _writes() == before + 1


async def test_autonomous_executes_without_a_person() -> None:
    result = await run(TENANT, "proc-quote", tier_override="AUTONOMOUS")
    assert result["outcome"]["outcome"] == "executed"


# ---------------------------------------------------------------- verdict gate
async def test_policy_violation_escalates_even_at_autonomous() -> None:
    result = await run(TENANT, "proc-quote-invoice", tier_override="AUTONOMOUS")
    assert result["verdict"]["decision"] == "escalate"
    assert result["outcome"]["outcome"] == "held"
    assert any(v["rule_id"] == "POL-003" for v in result["simulation"]["violations"])


async def test_blocking_policy_is_rejected_and_never_writes() -> None:
    before = await _writes()
    result = await run(TENANT, "proc-export", tier_override="AUTONOMOUS")
    assert result["verdict"]["decision"] == "reject"
    assert result["outcome"]["outcome"] == "refused"
    assert await _writes() == before


async def test_actor_and_verifier_are_different_vendors() -> None:
    result = await run(TENANT, "proc-quote", tier_override="SUGGEST")
    actor = result["action"]["actor_model"]["vendor"]
    verifier = result["verdict"]["verifier_model"]["vendor"]
    assert actor != verifier


# ---------------------------------------------------------------- kill switch
async def test_tenant_pause_refuses_every_write() -> None:
    await _set_paused(True)
    try:
        before = await _writes()
        result = await run(TENANT, "proc-quote", tier_override="AUTONOMOUS", approval=APPROVER)
        assert result["outcome"]["outcome"] == "refused"
        assert "kill switch" in result["outcome"]["title"].lower()
        assert await _writes() == before
    finally:
        await _set_paused(False)


async def test_pause_is_recorded_as_a_refusal() -> None:
    await _set_paused(True)
    try:
        await run(TENANT, "proc-quote", tier_override="AUTONOMOUS", approval=APPROVER)
    finally:
        await _set_paused(False)
    recent = await ledger.entries(TENANT, "proc-quote", entry_type="refusal", limit=1)
    assert recent and recent[0].entry_type == "refusal"


# ---------------------------------------------------------------- ledger
async def test_every_run_appends_to_the_chain_and_it_verifies() -> None:
    before = await ledger.verify_chain(TENANT, "proc-quote")
    await run(TENANT, "proc-quote", tier_override="SUGGEST")
    after = await ledger.verify_chain(TENANT, "proc-quote")
    assert after.entries == before.entries + 1
    assert after.ok


async def test_ledger_rows_cannot_be_updated_or_deleted() -> None:
    async with tenant_conn(TENANT) as conn:
        row = await conn.fetchrow(
            "SELECT seq FROM ledger_entries WHERE tenant_id=$1 LIMIT 1", TENANT
        )
        assert row is not None
        with pytest.raises(Exception, match="append-only"):
            await conn.execute(
                "UPDATE ledger_entries SET payload='{}'::jsonb WHERE seq=$1", row["seq"]
            )


async def test_no_execution_without_a_stored_verdict() -> None:
    """The database refuses it: executions.verdict_id is NOT NULL."""
    action, _ = await propose(TENANT, "proc-quote")
    async with tenant_conn(TENANT) as conn:
        with pytest.raises(Exception):  # noqa: B017 - asyncpg raises a NotNullViolation
            await conn.execute(
                "INSERT INTO executions (id, tenant_id, action_id, verdict_id, write_result)"
                " VALUES (gen_random_uuid(), $1, $2, NULL, '{}'::jsonb)",
                TENANT,
                action.id,
            )


# ---------------------------------------------------------------- reversal
async def test_execution_can_be_reversed_and_is_recorded() -> None:
    result = await run(TENANT, "proc-quote", tier_override="ACT_WITH_APPROVAL", approval=APPROVER)
    assert result["outcome"]["outcome"] == "executed"
    async with tenant_conn(TENANT) as conn:
        row = await conn.fetchrow(
            "SELECT id FROM executions WHERE tenant_id=$1 AND action_id=$2",
            TENANT,
            result["action"]["id"],
        )
    assert row is not None
    record = await executor.reverse(TENANT, str(row["id"]), APPROVER)
    assert record.entry_type == "reversal"
    entries = await ledger.entries(TENANT, "proc-quote", entry_type="reversal", limit=1)
    assert entries


# ---------------------------------------------------------------- PII on the write path
async def test_written_record_contains_no_tokens() -> None:
    """Tokens are restored inside the executor; a customer system never receives one."""
    await run(TENANT, "proc-quote", tier_override="AUTONOMOUS")
    records = await get_adapter("clickup").records(TENANT)
    assert records
    blob = str(records[0]["fields"])
    assert "<PERSON_" not in blob
    assert "<EMAIL_" not in blob


async def test_tier_enum_ordering_is_explicit() -> None:
    assert Tier.OBSERVE < Tier.SUGGEST < Tier.ACT_WITH_APPROVAL < Tier.AUTONOMOUS
