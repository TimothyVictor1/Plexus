"""Process discovery (spec 02, AT-02-1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from adapters._contract.base import ActorRef, SourceRef
from agents.discover.miner import build_cases, mine
from core.events.model import ObjectRef, PlexusEvent

T0 = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)


def ev(case: str, verb: str, day: float, actor: str = "<PERSON_0001>") -> PlexusEvent:
    return PlexusEvent(
        tenant_id="t",
        ts=T0 + timedelta(days=day),
        actor=ActorRef(token=actor, kind="person"),
        verb=verb,
        objects=[ObjectRef(object_type="quote", object_id=case)],
        source=SourceRef(source_id="gmail", external_id=f"{case}-{verb}"),
    )


def quote_case(n: int, offset: float) -> list[PlexusEvent]:
    """The ground-truth flow: enquiry, quote, acceptance, task, invoice."""
    c = f"q{n}"
    return [
        ev(c, "requested", offset + 0),
        ev(c, "offered", offset + 2),
        ev(c, "accepted", offset + 5),
        ev(c, "created", offset + 5.1),
        ev(c, "invoiced", offset + 30),
    ]


def test_cases_group_by_shared_objects() -> None:
    events = [e for n in range(6) for e in quote_case(n, n * 9)]
    cases = build_cases(events)
    assert len(cases) == 6
    assert all(len(c.events) == 5 for c in cases)


def test_events_without_a_shared_object_stay_separate() -> None:
    events = [ev("a", "requested", 0), ev("b", "offered", 1)]
    # Each case has a single event, so neither forms a case (a case needs at least two).
    assert build_cases(events) == []


def test_miner_recovers_the_ground_truth_order() -> None:
    events = [e for n in range(12) for e in quote_case(n, n * 9)]
    result = mine(build_cases(events), "quote_to_payment", "Enquiry to quote to invoice")
    assert [s.verb for s in result.steps] == [
        "requested",
        "offered",
        "accepted",
        "created",
        "invoiced",
    ]
    assert result.case_count == 12


def test_cycle_time_within_ten_percent_of_ground_truth() -> None:
    events = [e for n in range(12) for e in quote_case(n, n * 9)]
    result = mine(build_cases(events), "quote_to_payment", "Q")
    expected = 30 * 86400.0  # first event to last, 30 days
    actual = float(result.metrics["median_cycle_time_s"])
    assert abs(actual - expected) / expected < 0.10


def test_bottleneck_is_the_longest_gap() -> None:
    events = [e for n in range(12) for e in quote_case(n, n * 9)]
    result = mine(build_cases(events), "quote_to_payment", "Q")
    assert result.metrics["bottleneck_step"] == "invoiced"


def test_noise_edges_are_dropped() -> None:
    """An edge seen once, against a strong opposite flow, is not a real ordering."""
    events = [e for n in range(12) for e in quote_case(n, n * 9)]
    events += [ev("q0", "invoiced", 0.5), ev("q0", "requested", 0.6)]
    result = mine(build_cases(events), "quote_to_payment", "Q")
    pairs = {(e.source, e.target) for e in result.edges}
    assert ("invoiced", "requested") not in pairs


def test_dependency_measure_is_bounded() -> None:
    events = [e for n in range(12) for e in quote_case(n, n * 9)]
    result = mine(build_cases(events), "quote_to_payment", "Q")
    assert all(0.0 < e.dependency <= 1.0 for e in result.edges)
