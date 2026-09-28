"""The digital twin: the model, and the what-ifs run against it."""

from __future__ import annotations

import pytest

from twin.organisation import (
    OrgModel,
    build_model,
    demand_changes,
    person_leaves,
    process_changes,
    pseudonym,
)

pytestmark = pytest.mark.integration

TENANT = "demo"


@pytest.fixture
async def model() -> OrgModel:
    """Rebuilt for each test.

    Every test runs in its own event loop and the database pool is reset between them, so a
    model built once for the whole module would hold connections bound to a loop that has
    already closed.
    """
    return await build_model(TENANT)


async def test_the_model_is_built_from_what_actually_happened(model: OrgModel) -> None:
    assert model.people, "the demo has people doing work"
    assert model.processes
    assert model.total_events > 0
    assert model.window_days > 0


async def test_people_are_pseudonymous_not_named(model: OrgModel) -> None:
    """The boundary that keeps names from models keeps them from this view too."""
    for person in model.people:
        assert person.label.startswith("Person ")
        assert "@" not in person.label
        assert "<" not in person.label


def test_pseudonyms_keep_counting_past_z() -> None:
    assert pseudonym(0) == "Person A"
    assert pseudonym(25) == "Person Z"
    assert pseudonym(26) == "Person AA"


async def test_the_model_names_where_the_company_is_thin(model: OrgModel) -> None:
    assert model.risks, "specialised work should surface single points"
    for risk in model.risks:
        assert risk.text
        assert risk.person.startswith("Person ")
        assert 0.0 <= risk.share <= 1.0


async def test_losing_a_sole_owner_stops_that_step(model: OrgModel) -> None:
    sole = next((p for p in model.people if p.sole_owner_of), None)
    assert sole is not None, "the demo has at least one step only one person does"
    scenario = person_leaves(model, sole.token)
    assert any(e.severity == "stops" for e in scenario.effects)
    assert "stop" in scenario.summary.lower()


async def test_a_scenario_always_says_what_it_rests_on(model: OrgModel) -> None:
    """An answer without its assumptions invites being mistaken for a fact."""
    for scenario in (
        person_leaves(model, model.people[0].token),
        demand_changes(model, model.processes[0].id, 3.0),
    ):
        assert scenario.assumptions
        assert scenario.summary


async def test_an_unknown_person_is_reported_not_guessed(model: OrgModel) -> None:
    scenario = person_leaves(model, "<PERSON_nobody>")
    assert scenario.effects == []
    assert "nobody" in scenario.summary.lower()


async def test_more_work_never_claims_to_know_capacity(model: OrgModel) -> None:
    """Observed throughput is how work was shared, not how much anyone could do."""
    scenario = demand_changes(model, model.processes[0].id, 3.0)
    blob = " ".join([scenario.summary, *(e.text for e in scenario.effects)]).lower()
    assert "would take" not in blob
    assert any("not how many people" in a for a in scenario.assumptions)


async def test_less_work_is_never_reported_as_pressure(model: OrgModel) -> None:
    scenario = demand_changes(model, model.processes[0].id, 0.5)
    assert all(e.severity == "fine" for e in scenario.effects)


async def test_cutting_the_longest_wait_shortens_the_whole_thing(model: OrgModel) -> None:
    from core.processes import get_process

    detail = await get_process(TENANT, "quote_to_payment")
    assert detail is not None
    waits = [(w.from_step, w.to_step, w.duration.seconds) for w in detail.waits]
    scenario = process_changes(model, "quote_to_payment", waits, speed_up_percent=50)
    assert "faster" in scenario.summary
    assert any(
        e.before and e.after and e.after.seconds < e.before.seconds for e in scenario.effects
    )


async def test_changing_nothing_changes_nothing(model: OrgModel) -> None:
    from core.processes import get_process

    detail = await get_process(TENANT, "quote_to_payment")
    assert detail is not None
    waits = [(w.from_step, w.to_step, w.duration.seconds) for w in detail.waits]
    scenario = process_changes(model, "quote_to_payment", waits)
    assert scenario.effects == []
