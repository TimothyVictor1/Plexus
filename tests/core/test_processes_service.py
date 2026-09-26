"""Health, wording and durations as a person reads them (redesign B2, B3)."""

from __future__ import annotations

import pytest

from core.language.format import humanise
from core.language.service import ProcessShape, clean_phrase, rule_based
from core.processes.service import classify_health

DAY = 86400.0


def gaps(*days: float) -> list[float]:
    return [d * DAY for d in days]


# ---------------------------------------------------------------- health
def test_one_dominant_wait_is_slow() -> None:
    # Quote to payment: 2, 3, 26, 5 days. The invoice wait dwarfs the rest.
    assert classify_health(gaps(2, 3, 26, 5)) == "slow"


def test_a_mildly_uneven_process_is_worth_watching() -> None:
    assert classify_health(gaps(3, 1, 2)) == "watch"
    assert classify_health(gaps(5, 2, 3)) == "watch"


def test_evenly_paced_work_is_smooth_however_long_it_takes() -> None:
    """A long process is not a broken one. Only imbalance is worth flagging."""
    assert classify_health(gaps(2, 2)) == "smooth"
    assert classify_health(gaps(1, 1)) == "smooth"
    assert classify_health(gaps(9, 9, 9)) == "smooth"


def test_share_of_total_would_have_been_the_wrong_test() -> None:
    """Two equal waits each take half the time, which share-of-total would call a bottleneck."""
    assert classify_health(gaps(2, 2)) == "smooth"


def test_a_fortnight_of_dead_time_is_slow_even_when_balanced() -> None:
    assert classify_health(gaps(20, 20)) == "slow"


def test_no_waits_is_smooth() -> None:
    assert classify_health([]) == "smooth"
    assert classify_health(gaps(0)) == "smooth"


# ---------------------------------------------------------------- durations
@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (1.0, "about a day"),
        (1.5, "about a day and a half"),
        (2.0, "about 2 days"),
        (6.0, "about 6 days"),
        (26.0, "about 4 weeks"),
        (90.0, "about 3 months"),
    ],
)
def test_durations_read_like_speech(days: float, expected: str) -> None:
    assert humanise(days * DAY) == expected


def test_no_duration_is_not_rendered_as_zero() -> None:
    assert humanise(0) == "no time at all"


# ---------------------------------------------------------------- wording
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("slowest: waiting for approval.", "waiting for approval"),
        ("Slowest: Waiting for the invoice", "waiting for the invoice"),
        ("The longest wait is sending the invoice", "sending the invoice"),
        ("waiting for a reply", "waiting for a reply"),
    ],
)
def test_the_screen_never_says_slowest_twice(raw: str, expected: str) -> None:
    assert clean_phrase(raw) == expected


def shape() -> ProcessShape:
    return ProcessShape(
        process_id="p",
        step_verbs=["offered", "accepted", "delivered", "invoiced", "paid"],
        step_counts=[18] * 5,
        transitions=[{"from": "delivered", "to": "invoiced", "wait": "about 4 weeks"}],
        bottleneck_from="delivered",
        bottleneck_to="invoiced",
        bottleneck_wait="about 4 weeks",
        total_wait="about 5 weeks",
        case_count=18,
        tools=["email"],
    )


def test_rules_alone_produce_readable_english() -> None:
    """With no model reachable and nothing cached, the screen must still make sense."""
    language = rule_based(shape())
    assert language.source == "rules"
    assert language.name == "From quote sent to paid"
    assert language.steps == ["Quote sent", "Accepted", "Work done", "Invoice sent", "Paid"]
    assert language.slowest_text == "sending the invoice after the work is done"
    assert language.help_tip


def test_no_jargon_reaches_the_reader() -> None:
    banned = {
        "mined",
        "event log",
        "dependency",
        "variant",
        "rung",
        "trust score",
        "blast radius",
        "pii",
        "adapter",
        "tier",
        "bottleneck",
        "transition",
    }
    language = rule_based(shape())
    blob = " ".join(
        [
            language.name,
            language.description,
            language.slowest_text,
            language.help_tip,
            *language.steps,
        ]
    ).lower()
    assert not [w for w in banned if w in blob]


def test_the_signature_changes_when_the_shape_does() -> None:
    """Wording is cached against the structure, so a changed process gets re-described."""
    first = shape()
    second = first.model_copy(update={"step_verbs": [*first.step_verbs, "resolved"]})
    assert first.signature() != second.signature()
    assert first.signature() == shape().signature()
