"""Hash-chain integrity (spec 04, AT-04-2). Pure-function level: no database needed."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from core.ledger.ledger import GENESIS, canonical, entry_hash

TS = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
ACTOR: Mapping[str, object] = {"kind": "system", "id": "executor"}


def h(prev: str, payload: Mapping[str, object], entry_id: str = "e1") -> str:
    return entry_hash(prev, "t", "p", "execution", ACTOR, payload, TS, entry_id)


def test_hash_is_deterministic() -> None:
    assert h(GENESIS, {"a": 1}) == h(GENESIS, {"a": 1})


def test_payload_change_changes_the_hash() -> None:
    assert h(GENESIS, {"a": 1}) != h(GENESIS, {"a": 2})


def test_prev_hash_change_changes_the_hash() -> None:
    assert h(GENESIS, {"a": 1}) != h("f" * 64, {"a": 1})


def test_entry_id_change_changes_the_hash() -> None:
    assert h(GENESIS, {"a": 1}, "e1") != h(GENESIS, {"a": 1}, "e2")


def test_canonical_json_is_key_order_independent() -> None:
    assert canonical({"b": 2, "a": 1}) == canonical({"a": 1, "b": 2})


def test_tampering_breaks_verification() -> None:
    """Recomputing a tampered row's hash no longer matches what was stored."""
    stored_payload = {"amount": 100}
    stored_hash = h(GENESIS, stored_payload)
    tampered_payload = {"amount": 100, "tampered": True}
    assert h(GENESIS, tampered_payload) != stored_hash


def test_chain_links_forward() -> None:
    first = h(GENESIS, {"n": 1}, "e1")
    second = entry_hash(first, "t", "p", "approval", ACTOR, {"n": 2}, TS, "e2")
    # Rewriting the first entry invalidates every hash after it.
    rewritten = h(GENESIS, {"n": 99}, "e1")
    recomputed = entry_hash(rewritten, "t", "p", "approval", ACTOR, {"n": 2}, TS, "e2")
    assert recomputed != second
