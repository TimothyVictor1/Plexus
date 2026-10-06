"""The same scenario, read a second way.

A what-if answer has always said what breaks and how much slower it gets. That is the right
answer for whoever runs the work and the wrong one for whoever signs for it: "invoicing slows
by three weeks" and "about 90,000 SEK sits uncollected for three weeks longer" are the same
fact told to two different people.

So a scenario keeps its operational answer and gains a second, chosen one. A lens never
invents a number. Where the records cannot answer — most work carries no amount at all — it
says which records would be needed instead of estimating.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from twin.organisation import OrgModel, Scenario

LensId = Literal["operations", "cash", "people", "risk"]


class LensOption(BaseModel):
    id: str
    label: str
    blurb: str


# What a person picks from before running a scenario. Deliberately four and not seven: each
# one here can be answered from the event log as it actually is. A "customers" lens is the
# obvious fifth and is missing on purpose — the log records what was done, not who it was done
# for, so every number in it would be invented.
LENSES: list[LensOption] = [
    LensOption(
        id="operations",
        label="How work runs",
        blurb="Which steps stop, which slow down, and who could cover.",
    ),
    LensOption(
        id="cash",
        label="Money and cash",
        blurb="What it does to money already moving through the work.",
    ),
    LensOption(
        id="people",
        label="People and load",
        blurb="Who absorbs the work, and how much more each person carries.",
    ),
    LensOption(
        id="risk",
        label="Risk and continuity",
        blurb="What becomes fragile, and what rests on one person afterwards.",
    ),
]


class LensFinding(BaseModel):
    label: str
    value: str
    detail: str = ""


class LensView(BaseModel):
    id: str
    label: str
    summary: str
    findings: list[LensFinding] = Field(default_factory=list)
    # Set when the records cannot honestly answer this lens for this scenario. The screen shows
    # it instead of findings, so an empty answer always says why it is empty.
    unavailable: str = ""


def _money(amount: float, currency: str) -> str:
    unit = currency or "SEK"
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M {unit}"
    if amount >= 10_000:
        return f"{amount / 1000:,.0f}k {unit}"
    return f"{amount:,.0f} {unit}"


def _days(seconds: float) -> str:
    d = seconds / 86_400
    if d >= 14:
        return f"{d / 7:.0f} weeks"
    if d >= 1.5:
        return f"{d:.0f} days"
    return f"{d * 24:.0f} hours"


def _cash(model: OrgModel, scenario: Scenario) -> LensView:
    """Money is not made slower or faster; it is held up for longer or less long.

    The rate is what the records actually show over the window — total recorded against the
    window's length — so a process with no amounts produces no number rather than a guess.

    One slip per process, not one per step. The same invoices run through every step of the
    work they belong to, so adding a delay at two steps counts the same money twice; the
    figure that means anything is the worst single slip the money has to wait through.
    """
    by_id = {p.id: p for p in model.processes}

    # Volume scenarios say nothing about durations on purpose, so there is no slip to price.
    # What can be said is how much more money would be riding on the same work.
    if scenario.kind == "demand_changes" and scenario.magnitude:
        touched = {e.process_id for e in scenario.effects}
        priced = [by_id[i] for i in touched if i in by_id and by_id[i].money]
        if not priced:
            names = ", ".join(sorted({by_id[i].name for i in touched if i in by_id}))
            return LensView(
                id="cash",
                label="Money and cash",
                summary="",
                unavailable=(
                    f"{names or 'This work'} carries no amounts in its records, so there is no "
                    "money here to follow. Connect the accounting tool and this fills in."
                ),
            )
        volume: list[LensFinding] = []
        total_now = total_then = 0.0
        unit = ""
        for priced_process in priced:
            then = priced_process.money * scenario.magnitude
            total_now += priced_process.money
            total_then += then
            unit = unit or priced_process.currency
            volume.append(
                LensFinding(
                    label=priced_process.name,
                    value=f"{_money(then, priced_process.currency)} instead of "
                    f"{_money(priced_process.money, priced_process.currency)}",
                    detail=(
                        f"Over {model.window_days} days, across "
                        f"{priced_process.money_events} records. The same steps would carry "
                        f"{scenario.magnitude:g} times the money."
                    ),
                )
            )
        verb = "more" if scenario.magnitude > 1 else "less"
        return LensView(
            id="cash",
            label="Money and cash",
            summary=(
                f"About {_money(abs(total_then - total_now), unit)} {verb} money would move "
                f"through this work over {model.window_days} days, on the same steps and "
                "the same people."
            ),
            findings=volume,
        )

    worst: dict[str, tuple[float, str]] = {}
    silent: list[str] = []

    for effect in scenario.effects:
        process = by_id.get(effect.process_id)
        if process is None:
            continue
        if not process.money:
            if process.name not in silent:
                silent.append(process.name)
            continue
        if effect.before is None or effect.after is None:
            continue
        extra = effect.after.seconds - effect.before.seconds
        if extra <= 0:
            continue
        if extra > worst.get(effect.process_id, (0.0, ""))[0]:
            worst[effect.process_id] = (extra, effect.step)

    findings: list[LensFinding] = []
    total = 0.0
    unit = ""
    for process_id, (extra, step) in sorted(worst.items(), key=lambda kv: -kv[1][0]):
        process = by_id[process_id]
        per_day = process.money / max(model.window_days, 1)
        # Money cannot be held up for longer than there is money to hold up.
        held = min(per_day * (extra / 86_400), process.money)
        total += held
        unit = unit or process.currency
        findings.append(
            LensFinding(
                label=process.name,
                value=f"{_money(held, process.currency)} held up longer",
                detail=(
                    f"{_money(process.money, process.currency)} moved through this in the last "
                    f"{model.window_days} days, across {process.money_events} records. The worst "
                    f"slip is {step}, by about {_days(extra)}."
                ),
            )
        )

    if not findings:
        reason = (
            "None of the work this touches has amounts in its records"
            + (f" — {', '.join(silent)} carry none" if silent else "")
            + ". Connect the accounting tool and this fills in."
        )
        return LensView(id="cash", label="Money and cash", summary="", unavailable=reason)

    summary = f"About {_money(total, unit)} would sit longer than it does now."
    if silent:
        summary += f" {', '.join(silent)} carries no amounts, so it is not counted."
    return LensView(id="cash", label="Money and cash", summary=summary, findings=findings)


def _people(model: OrgModel, scenario: Scenario) -> LensView:
    """Work does not disappear when a person does; it lands on whoever is left."""
    findings: list[LensFinding] = []

    if scenario.kind == "person_leaves":
        stopped = [e for e in scenario.effects if e.severity == "stops"]
        slowed = [e for e in scenario.effects if e.severity == "slower"]
        if stopped:
            findings.append(
                LensFinding(
                    label="Nobody else has done this",
                    value=f"{len(stopped)} steps",
                    detail=", ".join(f"{e.step} in {e.process_name}" for e in stopped[:4]),
                )
            )
        if slowed:
            findings.append(
                LensFinding(
                    label="Would land on the people left",
                    value=f"{len(slowed)} steps",
                    detail=", ".join(f"{e.step} in {e.process_name}" for e in slowed[:4]),
                )
            )
        if scenario.cover:
            findings.append(
                LensFinding(
                    label="Could share it between them",
                    value=f"{len(scenario.cover)} people",
                    detail=", ".join(scenario.cover),
                )
            )
        if not findings:
            return LensView(
                id="people",
                label="People and load",
                summary="",
                unavailable="This person's work is already shared, so nothing moves to anyone.",
            )
        summary = (
            f"{len(stopped)} steps have nobody else; {len(slowed)} would be absorbed by others."
            if stopped
            else "Every step this person touches is shared with someone."
        )
        return LensView(id="people", label="People and load", summary=summary, findings=findings)

    # Demand and process changes move load without removing anybody.
    touched = {e.process_id for e in scenario.effects}
    for process in model.processes:
        if process.id not in touched:
            continue
        busiest = max(process.steps, key=lambda s: s.top_share, default=None)
        if busiest is None or busiest.top_share < 0.5:
            continue
        findings.append(
            LensFinding(
                label=process.name,
                value=f"{busiest.top_share * 100:.0f}% on one person",
                detail=(
                    f"{busiest.label} is handled mostly by one person, about "
                    f"{busiest.per_week:.0f} times a week. More volume lands there first."
                ),
            )
        )
    if not findings:
        return LensView(
            id="people",
            label="People and load",
            summary="",
            unavailable="No step here rests heavily enough on one person to single out.",
        )
    return LensView(
        id="people",
        label="People and load",
        summary="The load arrives where it is already concentrated.",
        findings=findings,
    )


def _risk(model: OrgModel, scenario: Scenario) -> LensView:
    """What is thin now, and what this would make thinner."""
    touched = {e.process_id for e in scenario.effects}
    relevant = [r for r in model.risks if any(p.name == r.process_name for p in model.processes)]
    stops = [e for e in scenario.effects if e.severity == "stops"]

    findings: list[LensFinding] = []
    if stops:
        findings.append(
            LensFinding(
                label="Would stop outright",
                value=f"{len(stops)} steps",
                detail=", ".join(f"{e.step} in {e.process_name}" for e in stops[:4]),
            )
        )
    sole = [r for r in relevant if r.kind == "single_point"]
    if sole:
        findings.append(
            LensFinding(
                label="Rests on one person today",
                value=f"{len(sole)} steps",
                detail=", ".join(f"{r.step} in {r.process_name}" for r in sole[:4]),
            )
        )
    heavy = [r for r in relevant if r.kind == "key_person"]
    if heavy:
        findings.append(
            LensFinding(
                label="Mostly one person today",
                value=f"{len(heavy)} steps",
                detail=", ".join(
                    f"{r.person} does {r.share * 100:.0f}% of {r.step}" for r in heavy[:3]
                ),
            )
        )
    if not findings:
        return LensView(
            id="risk",
            label="Risk and continuity",
            summary="",
            unavailable="Nothing this touches rests on one person, so nothing here is thin.",
        )
    summary = (
        f"{len(stops)} steps would stop and {len(sole)} already rest on one person."
        if stops
        else f"{len(sole) + len(heavy)} steps here already lean on one person."
    )
    _ = touched
    return LensView(id="risk", label="Risk and continuity", summary=summary, findings=findings)


def _operations(scenario: Scenario) -> LensView:
    stops = sum(1 for e in scenario.effects if e.severity == "stops")
    slower = sum(1 for e in scenario.effects if e.severity == "slower")
    fine = sum(1 for e in scenario.effects if e.severity == "fine")
    bits = []
    if stops:
        bits.append(f"{stops} would stop")
    if slower:
        bits.append(f"{slower} would slow")
    if fine:
        bits.append(f"{fine} would cope")
    return LensView(
        id="operations",
        label="How work runs",
        summary="; ".join(bits).capitalize() + "." if bits else "Nothing measurable moves.",
    )


def view(model: OrgModel, scenario: Scenario, lens: str) -> LensView:
    """The chosen reading of a scenario that has already been worked out."""
    if lens == "cash":
        return _cash(model, scenario)
    if lens == "people":
        return _people(model, scenario)
    if lens == "risk":
        return _risk(model, scenario)
    return _operations(scenario)
