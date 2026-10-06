"""The surveyor must describe a company it has never seen (agents/onboard/survey.py).

Every test here uses field names that appear nowhere in this repository's fixtures. That is
the point: the product has to plug into a company whose vocabulary nobody chose in advance,
and a surveyor that only works on data shaped like the demo is worse than none, because it
fails quietly.
"""

from __future__ import annotations

import pytest

from agents.onboard.profile import DataProfile, FieldKind, FieldProfile
from agents.onboard.survey import survey

pytestmark = pytest.mark.architecture


def test_it_finds_fields_in_a_vocabulary_it_has_never_seen() -> None:
    rows = [{"belopp": 8400, "valuta": "SEK", "mottagare": f"K{i}"} for i in range(30)]
    paths = {f.path for f in survey("swedish", rows)}
    assert paths == {"belopp", "valuta", "mottagare"}


def test_it_reaches_into_nested_payloads() -> None:
    rows = [{"rechnung": {"brutto_betrag": 1250.5, "waehrung": "EUR"}} for _ in range(10)]
    paths = {f.path for f in survey("german", rows)}
    assert "rechnung.brutto_betrag" in paths
    assert "rechnung.waehrung" in paths


def test_it_reaches_into_line_items() -> None:
    """Money very often lives one level inside a list, not at the top of the record."""
    rows = [{"invoice": {"lines": [{"total_cents": 129900, "iso_currency": "USD"}]}}] * 10
    paths = {f.path for f in survey("saas", rows)}
    assert "invoice.lines[].total_cents" in paths


def test_a_field_missing_from_some_records_is_reported_as_partly_filled() -> None:
    """Fill rate decides whether a field can be computed with, so it has to be honest."""
    rows = [{"a": 1, "b": 2} for _ in range(10)] + [{"a": 1} for _ in range(10)]
    by_path = {f.path: f for f in survey("mixed", rows)}
    assert by_path["a"].fill_rate == 1.0
    assert 0.0 < by_path["b"].fill_rate < 1.0


def test_it_measures_without_deciding_what_anything_means() -> None:
    """Interpretation belongs to the classifier. Keeping them apart keeps both checkable."""
    rows = [{"belopp": 8400, "valuta": "SEK"} for _ in range(10)]
    assert all(f.kind is FieldKind.unknown for f in survey("swedish", rows))
    assert all(f.confidence == 0.0 for f in survey("swedish", rows))


def test_every_measurement_carries_the_evidence_for_it() -> None:
    rows = [{"belopp": 8400} for _ in range(10)]
    assert survey("swedish", rows)[0].evidence


def test_an_empty_source_profiles_as_nothing_rather_than_failing() -> None:
    """A tool a company has connected but not used yet is normal, not an error."""
    assert survey("empty", []) == []


def test_it_does_not_walk_a_pathological_document_forever() -> None:
    deep: dict[str, object] = {"v": 1}
    for _ in range(40):
        deep = {"n": deep}
    assert survey("deep", [deep]) is not None


def test_a_profile_with_no_money_says_so_plainly() -> None:
    """Most work carries no figures. The product must be able to report that as a fact."""
    profile = DataProfile(
        tenant_id="t",
        fields=[FieldProfile(source_id="hr", path="start_date", kind=FieldKind.timestamp)],
    )
    assert profile.money_fields() == []
    assert profile.currencies() == []


def test_a_money_field_is_only_usable_when_it_is_both_confident_and_present() -> None:
    """A field found once in a thousand records cannot carry a financial figure."""
    rare = FieldProfile(
        source_id="s", path="x", kind=FieldKind.money, confidence=0.9, seen=1000, filled=3
    )
    unsure = FieldProfile(
        source_id="s", path="y", kind=FieldKind.money, confidence=0.2, seen=100, filled=100
    )
    good = FieldProfile(
        source_id="s", path="z", kind=FieldKind.money, confidence=0.8, seen=100, filled=90
    )
    assert not rare.usable and not unsure.usable and good.usable
    assert DataProfile(tenant_id="t", fields=[rare, unsure, good]).money_fields() == [good]
