"""The shadow workforce's record (core/shadow).

What these pin down is the honesty of the record rather than the cleverness of the agents. A
track record gathered at zero risk is the whole argument for ever letting an agent act, and a
record that can be flattered — by rewriting a prediction, by scoring twice, by counting the
ones nobody answered — argues for nothing.
"""

from __future__ import annotations

import pytest

from core.shadow.models import Scorecard
from core.shadow.service import EDIT_CREDIT, MIN_PREDICTIONS, READY_AT, _score, _verdict_for

pytestmark = pytest.mark.architecture


def card(agreed: int, edited: int, rejected: int) -> Scorecard:
    accuracy, weighted = _score(agreed, edited, rejected)
    settled = agreed + edited + rejected
    c = Scorecard(
        process_id="p",
        agent="a",
        predictions=settled,
        settled=settled,
        agreed=agreed,
        edited=edited,
        rejected=rejected,
        accuracy=accuracy,
        weighted=weighted,
        needs=max(MIN_PREDICTIONS - settled, 0),
    )
    c.ready = c.settled >= MIN_PREDICTIONS and c.weighted >= READY_AT
    return c


# ----------------------------------------------------------------- what a decision means
def test_an_untouched_approval_means_the_agent_was_right() -> None:
    assert _verdict_for("approved", edited=False)[0] == "agreed"


def test_an_edit_is_neither_right_nor_wrong() -> None:
    """Right idea, wrong words. Counting it as either would misrepresent the agent."""
    assert _verdict_for("approved", edited=True)[0] == "edited"


def test_skipping_means_it_should_not_have_happened() -> None:
    assert _verdict_for("skipped", edited=False)[0] == "rejected"


def test_an_undecided_item_says_nothing_about_the_agent() -> None:
    assert _verdict_for("open", edited=False)[0] == "pending"


def test_every_decision_carries_a_reason_a_person_can_read() -> None:
    for status in ("approved", "skipped"):
        assert _verdict_for(status, edited=False)[1]


# ----------------------------------------------------------------- the arithmetic
def test_accuracy_counts_only_what_was_actually_decided() -> None:
    """Pending predictions must not count in either direction.

    Otherwise an agent looks flawless by predicting things nobody ever decides.
    """
    assert _score(0, 0, 0) == (0.0, 0.0)
    assert _score(9, 0, 1)[0] == 0.9


def test_an_edit_is_worth_half_and_not_a_whole() -> None:
    _, weighted = _score(agreed=0, edited=10, rejected=0)
    assert weighted == EDIT_CREDIT


def test_being_right_a_few_times_in_a_row_earns_nothing() -> None:
    """Three for three is luck. The threshold exists so a lucky run proves nothing."""
    assert not card(agreed=3, edited=0, rejected=0).ready


def test_a_long_enough_record_at_a_high_enough_rate_earns_the_next_rung() -> None:
    assert card(agreed=MIN_PREDICTIONS, edited=0, rejected=0).ready


def test_a_long_record_of_being_wrong_earns_nothing() -> None:
    half = MIN_PREDICTIONS // 2
    assert not card(agreed=half, edited=0, rejected=MIN_PREDICTIONS - half).ready


def test_readiness_is_a_recommendation_and_not_a_promotion() -> None:
    """Earning the rung and being given it are separate. A person still decides."""
    ready = card(agreed=MIN_PREDICTIONS, edited=0, rejected=0)
    assert ready.ready
    # Nothing in the scorecard promotes anything; the tier lives in the ledger.
    assert not hasattr(ready, "tier")


# ----------------------------------------------------------------- what it says out loud
def test_an_agent_still_watching_says_how_much_further_it_has_to_go() -> None:
    from core.shadow.service import _verdict_text

    text = _verdict_text(card(agreed=5, edited=0, rejected=0))
    assert "to go" in text
    assert str(MIN_PREDICTIONS - 5) in text


def test_a_ready_agent_still_asks_rather_than_announces() -> None:
    from core.shadow.service import _verdict_text

    text = _verdict_text(card(agreed=MIN_PREDICTIONS, edited=0, rejected=0))
    assert "if you want" in text.lower()
