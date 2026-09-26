"""PII Boundary acceptance tests (spec 06, AT-06-1 and AT-06-3)."""

from __future__ import annotations

import json

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.pii.boundary import Boundary, TokenMap, learn_names, restore, scan
from core.pii.kms import KMS
from core.pii.recognisers import valid_orgnr, valid_personnummer
from scripts.fixtures.demo import check_digit, orgnr, pnr

TENANT = "testco"


class StubKMS(KMS):
    def data_key(self, tenant_id: str) -> bytes:
        return b"\x01" * 32 if tenant_id == TENANT else b"\x02" * 32


@pytest.fixture
def boundary() -> Boundary:
    return Boundary(StubKMS())


# ---------------------------------------------------------------- recognisers
@pytest.mark.parametrize("body", ["850312456", "771130239", "990101123", "010203040"])
def test_generated_personnummer_validate(body: str) -> None:
    assert valid_personnummer(pnr(body))


def test_personnummer_rejects_bad_check_digit() -> None:
    good = pnr("850312456")
    bad_digit = str((int(good[-1]) + 1) % 10)
    assert not valid_personnummer(good[:-1] + bad_digit)


def test_personnummer_rejects_impossible_date() -> None:
    assert not valid_personnummer(pnr("859912456"))


def test_orgnr_distinguished_from_personnummer() -> None:
    # A Swedish org number has a third digit of 2 or more; a personnummer's is a month.
    assert valid_orgnr(orgnr("556677889"))
    assert not valid_orgnr(pnr("850312456"))


# ---------------------------------------------------------------- tokenisation
def test_every_recogniser_type_is_caught(boundary: Boundary) -> None:
    learn_names(TENANT, ["Anna Lindqvist"])
    text = (
        f"Anna Lindqvist {pnr('850312456')} {orgnr('556677889')} "
        "+46 70 123 45 67 anna@example.se Hamngatan 14 "
        "SE45 5000 0000 0583 9825 7466"
    )
    tokenised, tmap = boundary.tokenize_text(text, tenant_id=TENANT)
    types = {etype for _, etype, _ in tmap.items_for_vault()}
    assert types >= {"PERSON", "PNR", "ORGNR", "PHONE", "EMAIL", "ADDRESS", "IBAN"}
    assert scan(tokenised, TENANT) == [], "tokenised text still contains PII"


def test_tokens_are_stable_within_a_tenant(boundary: Boundary) -> None:
    a, _ = boundary.tokenize_text("ring 073-884 21 09", tenant_id=TENANT)
    b, _ = boundary.tokenize_text("nummer: 073-884 21 09", tenant_id=TENANT)
    assert a.split()[-1] == b.split()[-1]


def test_tokens_differ_between_tenants(boundary: Boundary) -> None:
    a, _ = boundary.tokenize_text("073-884 21 09", tenant_id=TENANT)
    b, _ = boundary.tokenize_text("073-884 21 09", tenant_id="otherco")
    assert a != b


def test_restore_is_lossless(boundary: Boundary) -> None:
    original = f"Betala {orgnr('556677889')} på 073-884 21 09"
    tokenised, tmap = boundary.tokenize_text(original, tenant_id=TENANT)
    assert tokenised != original
    assert restore(tokenised, tmap) == original


def test_nested_structures_are_tokenised(boundary: Boundary) -> None:
    payload = {"to": "a@b.se", "meta": {"phones": ["073-884 21 09"]}, "n": 3}
    out, tmap = boundary.tokenize(payload, tenant_id=TENANT)
    blob = json.dumps(out)
    assert "a@b.se" not in blob
    assert "073-884 21 09" not in blob
    assert out["n"] == 3
    assert restore(out, tmap) == payload


def test_token_map_never_reveals_values() -> None:
    tmap = TokenMap()
    tmap.add("<PNR_0000>", "850312-4565", "PNR")
    assert "850312" not in repr(tmap)
    assert "850312" not in str(tmap)


# ---------------------------------------------------------------- fuzz (AT-06-1)
@st.composite
def text_with_pii(draw: st.DrawFn) -> tuple[str, str]:
    """A realistic PII value embedded in filler text.

    The dates and check digits are generated correctly on purpose: the recognisers validate
    both, so an invalid number is legitimately ignored and would not be a leak.
    """
    digits = "".join(draw(st.lists(st.sampled_from("0123456789"), min_size=9, max_size=9)))
    year = draw(st.integers(min_value=40, max_value=99))
    month = draw(st.integers(min_value=1, max_value=12))
    day = draw(st.integers(min_value=1, max_value=28))
    serial = digits[:3]
    kind = draw(st.sampled_from(["PNR", "ORGNR", "PHONE", "EMAIL", "IBAN"]))
    value = {
        "PNR": pnr(f"{year:02d}{month:02d}{day:02d}{serial}"),
        "ORGNR": orgnr(f"5566{digits[4:9]}"),
        "PHONE": f"07{digits[0]}-{digits[1:4]} {digits[4:6]} {digits[6:8]}",
        "EMAIL": f"user{digits[:3]}@example.se",
        "IBAN": "SE45 5000 0000 0583 9825 7466",
    }[kind]
    filler = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyzåäö .,\n", max_size=40))
    return f"{filler} {value} {filler}", value


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow], deadline=None)
@given(text_with_pii())
def test_fuzz_boundary_catches_and_restores(case: tuple[str, str]) -> None:
    text, value = case
    b = Boundary(StubKMS())
    tokenised, tmap = b.tokenize_text(text, tenant_id=TENANT)
    assert value not in tokenised, f"leaked {value!r}"
    assert restore(tokenised, tmap) == text


def test_check_digit_matches_luhn() -> None:
    assert check_digit("556677889") == "9"
    assert check_digit("850312456") == "5"
