"""Names are written in more forms than one (core/pii).

The gazetteer held full names and the matcher looked for exactly those, so "Nils Ahlgren" was
caught and "Hej Nils" was not. Almost nothing is written as a full name: people are greeted by
their first name and referred to by their surname. In the demo company's own records that left
a real first name in clear text in 141 stored documents.

These tests exist because that is the one failure the product cannot have. Everything else it
does is a convenience; not leaking a name is the promise.
"""

from __future__ import annotations

import pytest

from core.pii.boundary import Boundary, learn_names, name_aliases

pytestmark = pytest.mark.architecture


@pytest.fixture
def company() -> str:
    tenant = "name-forms-test"
    learn_names(
        tenant,
        ["Nils Ahlgren", "Petra Sundin", "Anna Lindqvist", "Anna Berg", "Sofia Ek"],
    )
    return tenant


def masked(tenant: str, text: str) -> str:
    return Boundary().tokenize_text(text, tenant_id=tenant)[0]


# ----------------------------------------------------------------- the leak itself
def test_a_first_name_in_a_greeting_is_masked(company: str) -> None:
    assert "Nils" not in masked(company, "Hej Nils,\n\nthanks for that.")


def test_a_surname_on_its_own_is_masked(company: str) -> None:
    assert "Ahlgren" not in masked(company, "Ahlgren signed it off yesterday.")


def test_a_full_name_is_still_masked(company: str) -> None:
    assert "Nils Ahlgren" not in masked(company, "Please ask Nils Ahlgren about it.")


# ----------------------------------------------------------------- without breaking meaning
def test_every_form_of_one_person_becomes_the_same_person(company: str) -> None:
    """The reason this is delicate.

    Masking a first name with a token of its own would turn one colleague into two, and the
    twin would report that nobody else has done work the same person did last week.
    """
    first = masked(company, "Nils")
    surname = masked(company, "Ahlgren")
    full = masked(company, "Nils Ahlgren")
    assert first == surname == full


def test_two_people_sharing_a_first_name_are_masked_but_not_guessed(company: str) -> None:
    """Guessing which Anna was meant is worse than admitting we cannot tell."""
    out = masked(company, "Anna said she would look at it.")
    assert "Anna" not in out
    assert out != masked(company, "Anna Lindqvist")
    assert out != masked(company, "Anna Berg")


def test_an_ordinary_word_is_not_mistaken_for_a_name(company: str) -> None:
    """ "Ek" is a surname and also the Swedish word for oak. Masking every oak would destroy
    the meaning of the text the masking exists to protect."""
    assert masked(company, "We planted an ek in the garden.") == ("We planted an ek in the garden.")


def test_a_name_inside_another_word_is_left_alone(company: str) -> None:
    """Word boundaries: a name is a word, not a substring."""
    assert "Annapurna" in masked(company, "They climbed Annapurna last year.")


# ----------------------------------------------------------------- the aliases themselves
def test_short_fragments_never_become_aliases(company: str) -> None:
    """Two letters are an ordinary word as often as a name."""
    assert "Ek" not in name_aliases(company)


def test_an_unambiguous_part_resolves_to_its_owner(company: str) -> None:
    assert name_aliases(company)["Sundin"] == "Petra Sundin"


def test_an_ambiguous_part_resolves_to_nobody(company: str) -> None:
    assert name_aliases(company)["Anna"] == "Anna"
