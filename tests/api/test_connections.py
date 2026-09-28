"""Connecting and disconnecting tools (redesign B8)."""

from __future__ import annotations

import pytest

from adapters.connectors import connect, disconnect, list_connections
from adapters.connectors.registry import CATEGORIES, NotConfiguredError, privacy_facts
from core.db.pool import tenant_conn

pytestmark = pytest.mark.integration

TENANT = "demo"


async def test_every_category_is_offered() -> None:
    found = await list_connections(TENANT)
    assert {c.category for c in found} == {c for c, _ in CATEGORIES}
    assert all(c.label and c.examples for c in found)


async def test_a_vendor_without_credentials_says_so_rather_than_offering_a_dead_button() -> None:
    found = {c.category: c for c in await list_connections(TENANT)}
    chat = found["chat"]
    assert chat.status == "not_configured"
    assert chat.detail


async def test_connecting_a_vendor_we_have_no_credentials_for_is_refused_clearly() -> None:
    with pytest.raises(NotConfiguredError) as exc:
        await connect(TENANT, "chat")
    assert "credentials" in str(exc.value).lower()


async def test_connected_tools_report_what_they_have_read() -> None:
    found = {c.category: c for c in await list_connections(TENANT)}
    assert found["email"].status == "connected"
    assert found["email"].document_count > 0


async def test_disconnecting_keeps_what_was_already_learned() -> None:
    """Detaching, not deleting: the processes and the ledger both depend on that history."""
    async with tenant_conn(TENANT) as conn:
        before = await conn.fetchval(
            "SELECT count(*) FROM documents d JOIN connections c ON c.id = d.connection_id"
            " WHERE d.tenant_id=$1 AND c.category='files'",
            TENANT,
        )
    assert int(before or 0) > 0

    result = await disconnect(TENANT, "files")
    assert result.status == "not_connected"

    async with tenant_conn(TENANT) as conn:
        after = await conn.fetchval(
            "SELECT count(*) FROM documents d JOIN connections c ON c.id = d.connection_id"
            " WHERE d.tenant_id=$1 AND c.category='files'",
            TENANT,
        )
    assert int(after or 0) == int(before or 0), "disconnect must not destroy what was learned"

    # Put it back so the demo stays whole.
    await connect(TENANT, "files")
    assert {c.category: c for c in await list_connections(TENANT)}["files"].status == "connected"


def test_privacy_claims_come_from_configuration_not_from_copy() -> None:
    """The page must never promise a residency the configuration does not actually give."""
    facts = {f["key"]: f for f in privacy_facts()}
    assert set(facts) == {"residency", "masking", "control"}
    assert facts["residency"]["ok"] in {"true", "false"}
    assert facts["residency"]["region"]
