"""Asking where a named thing has got to (core/ask/entities.py).

Document search answers "what was said". Where a project stands is not written in any document
— it is the shape of the events that touched it — so this is the retrieval that lets Ask answer
the question the product was described by: what is happening with a thing you can name.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.ask.entities import Entity, Moment, as_notes, names_in

pytestmark = pytest.mark.architecture


def moment(day: int, verb: str, actor: str = "Person A") -> Moment:
    return Moment(ts=datetime(2026, 6, day, tzinfo=UTC), verb=verb, actor=actor)


# ----------------------------------------------------------------- naming a thing
def test_an_identifier_survives_whole() -> None:
    """The bug this was written for.

    "expenses-034" split on the hyphen became "expenses" OR "034", so a question about one
    expense was answered about a different one. A near miss reads as the product being
    confidently wrong, not as a search result.
    """
    assert "expenses-034" in names_in("what is happening with expenses-034")


def test_several_names_in_one_question_are_all_found() -> None:
    found = names_in("compare expenses-034 with expenses-099")
    assert {"expenses-034", "expenses-099"} <= set(found)


def test_underscored_names_count_too() -> None:
    assert "quote_to_payment-007" in names_in("where has quote_to_payment-007 got to")


def test_a_question_naming_nothing_yields_no_names() -> None:
    assert names_in("how long does it take to get paid") == []


# ----------------------------------------------------------------- what it says back
def test_the_latest_thing_to_happen_leads_the_answer() -> None:
    entity = Entity(
        key="expenses-034",
        kind="expenses",
        label="expenses-034",
        events=3,
        timeline=[moment(16, "reimbursed"), moment(14, "approved"), moment(12, "submitted")],
        people=["Person A"],
    )
    assert "expenses-034" in entity.sentence()


def test_one_person_is_not_described_as_people() -> None:
    entity = Entity(
        key="e", kind="k", label="e", events=1, timeline=[moment(1, "done")], people=["Person A"]
    )
    assert "1 person has touched it" in entity.sentence()
    assert "1 people" not in entity.sentence()


def test_several_people_are_named() -> None:
    entity = Entity(
        key="e",
        kind="k",
        label="e",
        events=3,
        timeline=[moment(1, "done")],
        people=["Person A", "Person B"],
    )
    assert "2 people have touched it" in entity.sentence()


def test_an_entity_with_no_history_says_so_rather_than_guessing() -> None:
    bare = Entity(key="e", kind="k", label="e", events=0)
    assert "nothing recorded" in bare.sentence()


def test_notes_carry_the_timeline_the_answer_rests_on() -> None:
    """The model may only answer from these lines, so the dates have to be in them."""
    entity = Entity(
        key="expenses-034",
        kind="expenses",
        label="expenses-034",
        events=2,
        timeline=[moment(16, "reimbursed"), moment(12, "submitted")],
        people=["Person A"],
    )
    notes = as_notes([entity])
    assert "2026-06-16" in notes
    assert "reimbursed" in notes


def test_nothing_found_produces_no_notes_rather_than_an_empty_heading() -> None:
    assert as_notes([]) == ""
