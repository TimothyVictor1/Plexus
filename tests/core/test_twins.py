"""The twins, and the readiness that keeps them honest (twin/kinds, people, financial, general).

The rule these pin down: a twin that cannot be built from a company's data says so by name.
An empty panel is read as a fault, and the product loses the person's trust over something
that was only ever a missing connection.
"""

from __future__ import annotations

import pytest

from core.language.format import Duration
from twin.financial import build as build_financial
from twin.general import build as build_general
from twin.kinds import KINDS, TwinId
from twin.organisation import OrgModel, PersonModel, ProcessModel, StepRole
from twin.people import build as build_people
from twin.people import successor_brief

pytestmark = pytest.mark.architecture


def role(process: str, step: str, events: int, share: float, others: int) -> StepRole:
    return StepRole(
        process_id=process.lower().replace(" ", "_"),
        process_name=process,
        step=step,
        verb=step.lower(),
        events=events,
        share=share,
        others=others,
    )


def person(label: str, *roles: StepRole) -> PersonModel:
    return PersonModel(
        token=f"<P_{label}>",
        label=label,
        events=sum(r.events for r in roles),
        processes=sorted({r.process_id for r in roles}),
        roles=list(roles),
    )


def process(pid: str, name: str, money: float = 0.0, slow: str = "") -> ProcessModel:
    return ProcessModel(
        id=pid,
        name=name,
        cases=10,
        people=2,
        cycle=Duration(seconds=86_400, text="about a day"),
        money=money,
        currency="SEK" if money else "",
        money_events=5 if money else 0,
        slowest_step=slow,
        slowest_wait=Duration(seconds=172_800, text="about 2 days") if slow else None,
    )


# ----------------------------------------------------------------- one page, several twins
def test_a_general_twin_and_the_others_are_all_offered() -> None:
    ids = {k.id for k in KINDS}
    assert TwinId.general in ids
    assert {TwinId.operational, TwinId.financial, TwinId.people} <= ids


def test_the_general_twin_reports_each_twin_as_ready_or_explains_why_not() -> None:
    model = OrgModel(window_days=120, processes=[process("p", "Billing", money=1000, slow="Send")])
    cards = {c.id: c for c in build_general(model).cards}
    assert cards[TwinId.financial].readiness.ready
    # Nothing in this company describes software, and no inference should pretend otherwise.
    assert not cards[TwinId.technical].readiness.ready
    assert cards[TwinId.technical].readiness.reason
    assert cards[TwinId.technical].readiness.needs


def test_a_twin_that_cannot_be_built_never_renders_as_merely_empty() -> None:
    """The failure being guarded against: a blank panel read as a broken product."""
    empty = OrgModel(window_days=120)
    for card in build_general(empty).cards:
        if not card.readiness.ready:
            assert card.readiness.reason, f"{card.id} is blank with no explanation"


# ----------------------------------------------------------------- money
def test_money_is_never_summed_across_currencies() -> None:
    """Adding kronor to euros invents an exchange rate and hides it behind a decimal point."""
    model = OrgModel(
        window_days=120,
        processes=[
            process("a", "Billing", money=1000, slow="Send"),
            process("b", "Expenses", money=500, slow="Approve"),
        ],
    )
    model.processes[1].currency = "EUR"
    twin = build_financial(model)
    assert set(twin.currencies) == {"SEK", "EUR"}
    assert "1,000 SEK" in twin.summary and "500 EUR" in twin.summary


def test_a_company_with_no_amounts_is_told_so_by_name() -> None:
    model = OrgModel(window_days=120, processes=[process("hire", "Onboarding")])
    twin = build_financial(model)
    assert not twin.ready
    assert "Onboarding" in twin.reason


# ----------------------------------------------------------------- the handover
def test_work_only_one_person_has_done_comes_first_in_a_handover() -> None:
    """A successor needs the unteachable things first; the rest has someone to ask."""
    alone = role("Billing", "Quote", 12, 1.0, 0)
    mostly = role("Billing", "Invoice", 30, 0.85, 2)
    model = OrgModel(window_days=120, people=[person("Person A", mostly, alone)])
    twin = build_people(model).people[0]
    assert twin.handover[0].urgency == "only_them"
    assert twin.handover[0].step == "Quote"


def test_shared_work_is_left_out_of_a_handover() -> None:
    """Things three people already do are not what a resignation threatens."""
    shared = role("Billing", "Filing", 40, 0.3, 4)
    model = OrgModel(window_days=120, people=[person("Person A", shared)])
    assert build_people(model).people[0].handover == []


def test_a_brief_names_who_to_learn_from() -> None:
    mostly = role("Billing", "Invoice", 30, 0.85, 2)
    model = OrgModel(
        window_days=120,
        people=[
            person("Person A", mostly),
            person("Person B", role("Billing", "Invoice", 5, 0.15, 1)),
        ],
    )
    lines = successor_brief(build_people(model).people[0])
    assert any("Person B" in line for line in lines)


def test_one_other_person_is_not_described_as_people() -> None:
    model = OrgModel(window_days=120, people=[person("Person A", role("B", "Invoice", 30, 0.9, 1))])
    note = build_people(model).people[0].handover[0].note
    assert "1 other person has" in note
    assert "1 other people" not in note


def test_a_person_whose_work_is_entirely_shared_is_said_to_be_safe() -> None:
    model = OrgModel(window_days=120, people=[person("Person A", role("B", "Filing", 10, 0.2, 5))])
    assert "shared" in build_people(model).people[0].summary
