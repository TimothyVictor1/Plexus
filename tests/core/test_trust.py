"""Trust score and tier transitions (spec 04, AT-04-1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.ledger.models import LedgerEntry, Tier
from core.ledger.trust import TrustConfig, compute_trust, load_config, next_transition

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def entry(kind: str, days_ago: float = 0, **payload: object) -> LedgerEntry:
    return LedgerEntry(
        seq=0,
        id="00000000-0000-0000-0000-000000000000",
        tenant_id="t",
        process_id="p",
        entry_type=kind,
        actor={"kind": "system", "id": "x"},
        payload=payload,
        trace_id="",
        ts=NOW - timedelta(days=days_ago),
        prev_hash="0" * 64,
        hash="a" * 64,
    )


@pytest.fixture
def cfg():
    return load_config()


def test_forty_approvals_one_reversal_follows_the_formula(cfg: TrustConfig) -> None:
    """The brief's worked example: 40 approvals and 1 reversal."""
    entries = [entry("approval", days_ago=30 - i * 0.5) for i in range(40)]
    entries.append(entry("execution", days_ago=2))
    entries.append(entry("reversal", days_ago=1))
    b = compute_trust(entries, cfg, now=NOW)

    window = entries[-cfg.window_n :]
    approvals = sum(1 for e in window if e.entry_type == "approval")
    expected_approval_rate = approvals / approvals  # no rejections in the window
    assert b.approval_rate == pytest.approx(expected_approval_rate)
    assert b.reversal_rate == pytest.approx(1.0)  # 1 reversal over 1 execution
    assert b.trust == pytest.approx(
        cfg.weights["approval_rate"] * b.approval_rate
        + cfg.weights["reversal_rate"] * (1 - b.reversal_rate)
        + cfg.weights["recency"] * b.recency
        - cfg.weights["blast_radius"] * b.blast_radius
    )


def test_a_process_with_no_history_scores_zero(cfg: TrustConfig) -> None:
    """The bug this replaced: an untested process collected the clean-record terms for free."""
    b = compute_trust([], cfg, now=NOW)
    assert b.approval_rate == 0.0
    assert b.samples == 0
    assert b.trust == 0.0
    assert b.terms["reversal_rate"] == 0.0
    assert b.terms["recency"] == 0.0


def test_credit_is_withheld_just_below_the_threshold(cfg: TrustConfig) -> None:
    below = compute_trust(
        [entry("approval") for _ in range(cfg.min_decisions_for_credit - 1)], cfg, now=NOW
    )
    at = compute_trust(
        [entry("approval") for _ in range(cfg.min_decisions_for_credit)], cfg, now=NOW
    )
    assert below.terms["recency"] == 0.0
    assert at.terms["recency"] > 0.0
    assert at.trust > below.trust


def test_a_few_approvals_score_between_nothing_and_everything(cfg: TrustConfig) -> None:
    b = compute_trust([entry("approval") for _ in range(6)], cfg, now=NOW)
    assert 0.0 < b.trust < 1.0
    assert b.approval_rate == 1.0


def test_one_reversal_costs_more_than_it_gains(cfg: TrustConfig) -> None:
    clean = [entry("approval") for _ in range(10)] + [entry("execution") for _ in range(6)]
    reversed_run = [*clean, entry("reversal", days_ago=0)]
    assert (
        compute_trust(reversed_run, cfg, now=NOW).trust < compute_trust(clean, cfg, now=NOW).trust
    )


def test_a_recent_error_suppresses_the_recency_term(cfg: TrustConfig) -> None:
    entries = [entry("approval") for _ in range(10)]
    fresh = compute_trust([*entries, entry("reversal", days_ago=0)], cfg, now=NOW)
    healed = compute_trust([*entries, entry("reversal", days_ago=90)], cfg, now=NOW)
    assert fresh.terms["recency"] < healed.terms["recency"]


def test_blast_radius_reduces_trust(cfg: TrustConfig) -> None:
    clean = compute_trust([entry("approval", blast_radius=0.0)], cfg, now=NOW)
    wide = compute_trust([entry("approval", blast_radius=1.0)], cfg, now=NOW)
    assert wide.trust < clean.trust
    assert clean.trust - wide.trust == pytest.approx(cfg.weights["blast_radius"])


def test_recency_recovers_over_time(cfg: TrustConfig) -> None:
    fresh = compute_trust([entry("reversal", days_ago=0)], cfg, now=NOW)
    old = compute_trust([entry("reversal", days_ago=60)], cfg, now=NOW)
    assert old.recency > fresh.recency
    assert fresh.recency == pytest.approx(0.0, abs=1e-9)


@given(
    approvals=st.integers(min_value=0, max_value=30),
    rejections=st.integers(min_value=0, max_value=30),
)
def test_trust_always_within_bounds(approvals: int, rejections: int) -> None:
    cfg = load_config()
    entries = [entry("approval") for _ in range(approvals)]
    entries += [entry("rejection") for _ in range(rejections)]
    b = compute_trust(entries, cfg, now=NOW)
    assert 0.0 <= b.trust <= 1.0


def test_promotion_blocked_without_enough_samples(cfg: TrustConfig) -> None:
    entries = [entry("approval") for _ in range(3)]
    b = compute_trust(entries, cfg, now=NOW)
    t = next_transition(Tier.SUGGEST, b, cfg)
    assert not t.eligible
    assert any("decisions" in x for x in t.blockers)


def test_promotion_blocked_by_recent_reversal(cfg: TrustConfig) -> None:
    entries = [entry("approval") for _ in range(30)]
    b = compute_trust(entries, cfg, now=NOW)
    t = next_transition(Tier.SUGGEST, b, cfg, had_recent_reversal=True)
    assert not t.eligible
    assert any("reversal" in x for x in t.blockers)


def test_high_risk_is_capped_below_autonomous(cfg: TrustConfig) -> None:
    entries = [entry("approval") for _ in range(30)]
    b = compute_trust(entries, cfg, now=NOW)
    t = next_transition(Tier.ACT_WITH_APPROVAL, b, cfg, risk_class="high")
    assert t.direction == "hold"
    assert "cap" in t.reason
