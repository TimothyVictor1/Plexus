"""Trust score and tier transitions (spec 04).

The formula and every parameter come from config/trust.yaml. Changing them requires sign-off,
so nothing here hard-codes a weight.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from core.ledger.models import LedgerEntry, Tier, Transition, TrustBreakdown

CONFIG_PATH = Path("config/trust.yaml")


class TrustConfig(BaseModel):
    window_n: int
    min_decisions_for_credit: int = 5
    weights: dict[str, float]
    recency_tau_days: float
    no_reversal_days_for_promotion: int
    thresholds: dict[str, float]
    min_samples: dict[str, int]
    max_tier_for_risk_class: dict[str, str]

    def threshold(self, tier: Tier) -> float:
        return float(self.thresholds.get(tier.name, 1.0))

    def min_sample(self, tier: Tier) -> int:
        return int(self.min_samples.get(tier.name, 10**6))


@lru_cache(maxsize=1)
def load_config(path: str = str(CONFIG_PATH)) -> TrustConfig:
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cfg = TrustConfig(**data)
    w = cfg.weights
    if any(v < 0 for v in w.values()):
        msg = "trust weights must be non-negative"
        raise ValueError(msg)
    if w["approval_rate"] + w["reversal_rate"] + w["recency"] > 1.0 + 1e-9:
        msg = "positive trust weights must not sum above 1.0"
        raise ValueError(msg)
    return cfg


def compute_trust(
    entries: Sequence[LedgerEntry], cfg: TrustConfig, now: datetime | None = None
) -> TrustBreakdown:
    now = now or datetime.now(tz=UTC)
    window = list(entries)[-cfg.window_n :]

    approvals = sum(1 for e in window if e.entry_type == "approval")
    rejections = sum(1 for e in window if e.entry_type == "rejection")
    executions = sum(1 for e in window if e.entry_type == "execution")
    reversals = sum(1 for e in window if e.entry_type == "reversal")

    decisions = approvals + rejections
    approval_rate = approvals / decisions if decisions else 0.0
    reversal_rate = min(reversals / executions, 1.0) if executions else 0.0

    error_times = [e.ts for e in window if e.entry_type in {"reversal", "demotion"}]
    if error_times:
        days = max((now - max(error_times)).total_seconds() / 86400.0, 0.0)
        recency = 1 - math.exp(-days / cfg.recency_tau_days)
    else:
        days = None
        recency = 1.0

    radii = [
        float(e.payload.get("blast_radius", 0.0)) for e in window if "blast_radius" in e.payload
    ]
    blast = sum(radii) / len(radii) if radii else 0.0

    # Having no history is not the same as having a clean one, so the two terms that would
    # otherwise pay out in full to an untested process are withheld until it has a record.
    earned = decisions >= cfg.min_decisions_for_credit

    w = cfg.weights
    terms = {
        "approval_rate": w["approval_rate"] * approval_rate,
        "reversal_rate": w["reversal_rate"] * (1 - reversal_rate) if earned else 0.0,
        "recency": w["recency"] * recency if earned else 0.0,
        "blast_radius": -w["blast_radius"] * blast,
    }
    trust = min(1.0, max(0.0, sum(terms.values())))

    return TrustBreakdown(
        trust=trust,
        approval_rate=approval_rate,
        reversal_rate=reversal_rate,
        recency=recency,
        blast_radius=blast,
        samples=decisions,
        executions=executions,
        reversals=reversals,
        days_since_error=days,
        terms=terms,
    )


def next_transition(
    current: Tier,
    breakdown: TrustBreakdown,
    cfg: TrustConfig,
    *,
    risk_class: str = "low",
    had_recent_reversal: bool = False,
) -> Transition:
    cap = Tier.parse(cfg.max_tier_for_risk_class.get(risk_class, "AUTONOMOUS"))
    if current >= Tier.AUTONOMOUS or current >= cap:
        return Transition(
            direction="hold",
            from_tier=current.name,
            to_tier=current.name,
            reason=("at the cap for risk class " + risk_class) if current >= cap else "top tier",
        )

    nxt = Tier(current + 1)
    blockers: list[str] = []
    if breakdown.trust < cfg.threshold(nxt):
        blockers.append(f"trust {breakdown.trust:.2f} below {cfg.threshold(nxt):.2f}")
    if breakdown.samples < cfg.min_sample(nxt):
        blockers.append(f"{breakdown.samples} decisions, needs {cfg.min_sample(nxt)}")
    if had_recent_reversal:
        blockers.append(f"reversal within {cfg.no_reversal_days_for_promotion} days")

    return Transition(
        direction="promote" if not blockers else "hold",
        from_tier=current.name,
        to_tier=nxt.name,
        reason="eligible, awaiting approver confirmation" if not blockers else "; ".join(blockers),
        eligible=not blockers,
        blockers=blockers,
    )


def demotion_for(entry_type: str, current: Tier) -> Tier | None:
    """A reversal drops one tier; a policy violation in an execution drops to OBSERVE."""
    if entry_type == "reversal":
        return Tier(max(Tier.OBSERVE, current - 1))
    if entry_type == "policy_violation":
        return Tier.OBSERVE
    return None
