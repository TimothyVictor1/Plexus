"""Deciding what a company's fields mean (agents/onboard/classify.py).

Not one field name here appears in this repository's fixtures, and several are not in English.
A classifier that only recognises the vocabulary it was built against is the bug being fixed,
not the feature being added.
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.onboard.classify import classify, classify_one
from agents.onboard.profile import FieldKind, FieldProfile
from agents.onboard.survey import survey

pytestmark = pytest.mark.architecture


async def kinds(source: str, rows: list[dict[str, Any]]) -> dict[str, FieldKind]:
    return {f.path: f.kind for f in await classify(survey(source, rows))}


# ----------------------------------------------------------------- money, in any language
@pytest.mark.parametrize(
    ("rows", "money_path", "currency_path"),
    [
        ([{"belopp": 8400.00, "valuta": "SEK"}] * 30, "belopp", "valuta"),
        ([{"betrag": 1250.50, "waehrung": "EUR"}] * 30, "betrag", "waehrung"),
        ([{"montant": 99.99, "devise": "CHF"}] * 30, "montant", "devise"),
        ([{"zzz": 4200.00, "qqq": "AUD"}] * 30, "zzz", "qqq"),
    ],
)
async def test_money_is_found_whatever_it_is_called(
    rows: list[dict[str, Any]], money_path: str, currency_path: str
) -> None:
    """Including when the name means nothing at all — the structure is the evidence."""
    found = {f.path: f for f in await classify(survey("co", rows))}
    assert found[money_path].kind is FieldKind.money
    assert found[money_path].currency_path == currency_path
    assert found[currency_path].kind is FieldKind.currency


async def test_money_nested_inside_a_line_item_is_still_found() -> None:
    rows = [{"inv": {"lines": [{"tot": 129900, "cur": "USD"}]}}] * 30
    found = {f.path: f for f in await classify(survey("saas", rows))}
    assert found["inv.lines[].tot"].kind is FieldKind.money


async def test_a_currency_is_never_assumed_when_none_is_recorded() -> None:
    """Defaulting to a currency is how a German company's figures get labelled SEK."""
    rows = [{"total": 1250.50}] * 30
    found = {f.path: f for f in await classify(survey("co", rows))}
    assert found["total"].currencies == []
    assert found["total"].currency_path is None


# ----------------------------------------------------------------- not everything is money
async def test_a_count_beside_a_currency_is_not_treated_as_money() -> None:
    """The bug this was written for.

    One currency column sat beside two numbers and vouched for both, so a count of three items
    was read as three yen. With nothing structural to say which number is the money, the
    honest answer is to settle neither and let a model adjudicate.
    """
    rows = [{"kingaku": 48000, "kensuu": 3, "tsuuka": "JPY"}] * 30
    result = await kinds("jp", rows)
    assert result["kensuu"] is not FieldKind.money
    assert result["kingaku"] is not FieldKind.money
    assert result["tsuuka"] is FieldKind.currency


async def test_a_number_with_no_unit_anywhere_is_a_quantity() -> None:
    rows = [{"seats": 12, "closed_at": "2026-02-02T09:30:00"}] * 30
    result = await kinds("saas", rows)
    assert result["seats"] is FieldKind.quantity


async def test_dates_statuses_and_identities_are_told_apart() -> None:
    rows = [
        {"skickad": "2026-03-01T10:00:00", "status": "betald", "kund_nr": f"K{i}"}
        for i in range(30)
    ]
    result = await kinds("se", rows)
    assert result["skickad"] is FieldKind.timestamp
    assert result["status"] is FieldKind.status
    assert result["kund_nr"] is FieldKind.identity


# ----------------------------------------------------------------- the model's place
async def test_without_a_model_an_unsettled_field_stays_unsettled() -> None:
    """Unknown is a usable answer. A guess is not."""
    rows = [{"a": 48000, "b": 3, "cur": "JPY"}] * 30
    assert FieldKind.unknown in (await kinds("x", rows)).values()


async def test_the_model_is_only_asked_about_what_evidence_cannot_settle() -> None:
    asked: list[list[str]] = []

    async def adjudicate(fields: list[FieldProfile]) -> dict[str, FieldKind]:
        asked.append([f.path for f in fields])
        return {f.path: FieldKind.money for f in fields}

    rows = [{"belopp": 8400.00, "valuta": "SEK", "a": 48000, "b": 3}] * 30
    await classify(survey("se", rows), adjudicate)
    assert asked, "the adjudicator should have been consulted"
    assert "belopp" not in asked[0], "evidence already settled this one"
    assert "valuta" not in asked[0]


async def test_a_model_verdict_never_outranks_the_evidence() -> None:
    """A judgement about meaning is never as solid as a measurement, and says so."""

    async def adjudicate(fields: list[FieldProfile]) -> dict[str, FieldKind]:
        return {f.path: FieldKind.money for f in fields}

    rows = [{"a": 48000, "b": 3, "cur": "JPY"}] * 30
    out = {f.path: f for f in await classify(survey("x", rows), adjudicate)}
    settled = [f for f in out.values() if f.kind is FieldKind.money]
    assert settled and all(f.confidence <= 0.6 for f in settled)


async def test_every_decision_carries_the_reason_for_it() -> None:
    rows = [{"belopp": 8400.00, "valuta": "SEK"}] * 30
    assert all(f.evidence for f in await classify(survey("se", rows)))


def test_classifying_one_field_needs_no_model_and_no_network() -> None:
    bare = FieldProfile(source_id="s", path="x", seen=30, filled=30, numeric_share=1.0)
    assert classify_one(bare, [bare]).kind is FieldKind.quantity
