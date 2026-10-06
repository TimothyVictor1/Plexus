"""Reading a scenario a second way (twin/lenses.py).

The operational answer and the business answer describe the same arithmetic. What these pin
down is that the second reading never says more than the records support: money that is not
recorded is not estimated, and money that is recorded is not counted twice.
"""

from __future__ import annotations

import pytest

from core.language.format import Duration
from twin.lenses import LENSES, view
from twin.organisation import Effect, OrgModel, ProcessModel, Risk, Scenario

pytestmark = pytest.mark.architecture


def process(pid: str, name: str, money: float = 0.0, events: int = 0) -> ProcessModel:
    return ProcessModel(
        id=pid,
        name=name,
        cases=10,
        people=3,
        cycle=Duration(seconds=86_400, text="about a day"),
        money=money,
        currency="SEK" if money else "",
        money_events=events,
    )


def slip(pid: str, name: str, step: str, before_s: float, after_s: float) -> Effect:
    return Effect(
        process_id=pid,
        process_name=name,
        step=step,
        severity="slower",
        text="",
        before=Duration(seconds=before_s, text=""),
        after=Duration(seconds=after_s, text=""),
    )


def model(*processes: ProcessModel, risks: list[Risk] | None = None) -> OrgModel:
    return OrgModel(window_days=120, processes=list(processes), risks=risks or [])


# ----------------------------------------------------------------- the catalogue
def test_every_offered_lens_can_be_asked_for() -> None:
    m = model(process("p", "Billing", money=100_000, events=10))
    scenario = Scenario(kind="person_leaves", title="t", summary="s")
    for option in LENSES:
        assert view(m, scenario, option.id).id == option.id


def test_an_unknown_lens_falls_back_to_the_operational_one() -> None:
    m = model(process("p", "Billing"))
    assert view(m, Scenario(kind="person_leaves", title="t", summary="s"), "nonsense").id == (
        "operations"
    )


# ----------------------------------------------------------------- money
def test_money_is_never_invented_for_work_that_records_none() -> None:
    """Most work carries no amount. Saying so is the whole point."""
    m = model(process("hire", "New hire onboarding"))
    scenario = Scenario(
        kind="person_leaves",
        title="t",
        summary="s",
        effects=[slip("hire", "New hire onboarding", "Contract", 86_400, 864_000)],
    )
    lens = view(m, scenario, "cash")
    assert lens.unavailable
    assert "New hire onboarding" in lens.unavailable
    assert not lens.findings


def test_the_same_money_is_not_counted_once_per_slipping_step() -> None:
    """Invoices run through every step of their own process.

    Two steps slipping does not delay two sets of invoices, so the figure is the worst single
    slip, not the sum. Summing produced a number larger than the money that exists.
    """
    m = model(process("bill", "Billing", money=120_000, events=12))
    two_steps = Scenario(
        kind="person_leaves",
        title="t",
        summary="s",
        effects=[
            slip("bill", "Billing", "Invoice sent", 0, 30 * 86_400),
            slip("bill", "Billing", "Paid", 0, 10 * 86_400),
        ],
    )
    one_step = Scenario(
        kind="person_leaves",
        title="t",
        summary="s",
        effects=[slip("bill", "Billing", "Invoice sent", 0, 30 * 86_400)],
    )
    assert view(m, two_steps, "cash").summary == view(m, one_step, "cash").summary
    assert len(view(m, two_steps, "cash").findings) == 1


def test_money_held_up_cannot_exceed_the_money_there_is() -> None:
    """A slip longer than the window would otherwise price more money than ever moved."""
    m = model(process("bill", "Billing", money=50_000, events=5))
    scenario = Scenario(
        kind="person_leaves",
        title="t",
        summary="s",
        effects=[slip("bill", "Billing", "Invoice sent", 0, 3650 * 86_400)],
    )
    finding = view(m, scenario, "cash").findings[0]
    assert "50,000 SEK" in finding.value or "50k SEK" in finding.value


def test_more_volume_is_priced_as_volume_not_as_delay() -> None:
    """Demand scenarios carry no durations on purpose, so there is no slip to price.

    What can honestly be said is how much more money rides on the same steps.
    """
    m = model(process("bill", "Billing", money=100_000, events=10))
    scenario = Scenario(
        kind="demand_changes",
        title="t",
        summary="s",
        magnitude=3.0,
        effects=[
            Effect(
                process_id="bill",
                process_name="Billing",
                step="Invoice",
                severity="slower",
                text="",
            )
        ],
    )
    lens = view(m, scenario, "cash")
    assert not lens.unavailable
    assert "more" in lens.summary


def test_less_volume_reads_as_less_without_a_double_negative() -> None:
    m = model(process("bill", "Billing", money=100_000, events=10))
    scenario = Scenario(
        kind="demand_changes",
        title="t",
        summary="s",
        magnitude=0.5,
        effects=[
            Effect(
                process_id="bill",
                process_name="Billing",
                step="Invoice",
                severity="slower",
                text="",
            )
        ],
    )
    summary = view(m, scenario, "cash").summary
    assert "less" in summary
    assert "-" not in summary


# ----------------------------------------------------------------- the other readings
def test_an_empty_reading_always_says_why_it_is_empty() -> None:
    """A screen with nothing on it must explain itself, in every lens."""
    m = model(process("p", "Billing"))
    bare = Scenario(kind="person_leaves", title="t", summary="s")
    for lens_id in ("cash", "people", "risk"):
        lens = view(m, bare, lens_id)
        assert lens.findings or lens.unavailable, lens_id


def test_risk_counts_what_would_stop_outright() -> None:
    m = model(process("p", "Billing"))
    scenario = Scenario(
        kind="person_leaves",
        title="t",
        summary="s",
        effects=[
            Effect(process_id="p", process_name="Billing", step="Quote", severity="stops", text="")
        ],
    )
    lens = view(m, scenario, "risk")
    assert "1 steps" in lens.findings[0].value or "stop" in lens.summary
