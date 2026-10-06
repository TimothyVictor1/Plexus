"""The whole company in one view, and the readiness of each twin that makes it up.

The general twin is not a seventh model. It is the other twins placed side by side, with one
sentence from each, so a person can see the shape of the company before choosing which part to
look into. Composing rather than recomputing means the overview can never disagree with the
screen it links to — a dashboard that contradicts its own detail page is worse than no
dashboard.

Each twin reports whether it can be built from this company's data at all. A company with no
code tool connected has no technical twin, and is told exactly that rather than shown an empty
panel it will read as a fault.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from twin import financial as financial_twin
from twin import people as people_twin
from twin.kinds import KINDS, Readiness, TwinId
from twin.organisation import OrgModel


class TwinCard(BaseModel):
    """One twin, as it appears on the page where they are all chosen from."""

    id: TwinId
    label: str
    blurb: str
    readiness: Readiness
    headline: str = ""
    # A couple of numbers worth seeing without opening it.
    figures: list[str] = Field(default_factory=list)


class GeneralTwin(BaseModel):
    window_days: int
    people: int
    processes: int
    events: int
    summary: str = ""
    cards: list[TwinCard] = Field(default_factory=list)


def _operational(model: OrgModel) -> tuple[Readiness, str, list[str]]:
    if not model.processes:
        return (
            Readiness(
                ready=False,
                reason="No work has been seen yet, so there are no ways of working to describe.",
                needs=["a connected tool with some history in it"],
            ),
            "",
            [],
        )
    slow = [p for p in model.processes if p.slowest_wait]
    worst = max(slow, key=lambda p: p.slowest_wait.seconds if p.slowest_wait else 0, default=None)
    headline = f"{len(model.processes)} ways of working, found without being configured."
    figures = [f"{len(model.processes)} processes", f"{model.total_events} things done"]
    if worst and worst.slowest_wait:
        headline += (
            f" The longest wait anywhere is {worst.slowest_wait.text}, "
            f"at {worst.slowest_step} in {worst.name}."
        )
    return Readiness(ready=True), headline, figures


def _financial(model: OrgModel) -> tuple[Readiness, str, list[str]]:
    twin = financial_twin.build(model)
    if not twin.ready:
        return (
            Readiness(ready=False, reason=twin.reason, needs=["a tool that holds amounts"]),
            "",
            [],
        )
    return (
        Readiness(ready=True),
        twin.summary,
        [f"{m.total:,.0f} {m.currency}" for m in twin.at_rest[:2]],
    )


def _people(model: OrgModel) -> tuple[Readiness, str, list[str]]:
    twin = people_twin.build(model)
    if not twin.people:
        return (
            Readiness(
                ready=False,
                reason="Nobody has done anything in the window yet.",
                needs=["a connected tool with some history in it"],
            ),
            "",
            [],
        )
    return (
        Readiness(ready=True),
        twin.summary,
        [f"{len(twin.people)} people", f"{twin.only_one_person} steps rest on one person"],
    )


def _business(model: OrgModel) -> tuple[Readiness, str, list[str]]:
    if not model.external_parties:
        return (
            Readiness(
                ready=False,
                reason=(
                    "No clients or outside organisations have been seen in this company's "
                    "records yet."
                ),
                needs=["a tool that records who work is done for"],
            ),
            "",
            [],
        )
    return (
        Readiness(ready=True),
        f"{model.external_parties} outside organisations appear in this company's work.",
        [f"{model.external_parties} organisations"],
    )


def _technical(_: OrgModel) -> tuple[Readiness, str, list[str]]:
    # Honest by construction: nothing in this company's data describes software being built
    # until a code tool is connected, and no amount of inference changes that.
    return (
        Readiness(
            ready=False,
            reason="No code or delivery tool is connected, so there is nothing to model here.",
            needs=["a code host, a CI tool, or an issue tracker"],
        ),
        "",
        [],
    )


BUILDERS = {
    TwinId.operational: _operational,
    TwinId.financial: _financial,
    TwinId.people: _people,
    TwinId.business: _business,
    TwinId.technical: _technical,
}


def build(model: OrgModel) -> GeneralTwin:
    cards: list[TwinCard] = []
    for kind in KINDS:
        if kind.id is TwinId.general:
            continue
        readiness, headline, figures = BUILDERS[kind.id](model)
        cards.append(
            TwinCard(
                id=kind.id,
                label=kind.label,
                blurb=kind.blurb,
                readiness=readiness,
                headline=headline,
                figures=figures,
            )
        )

    ready = [c for c in cards if c.readiness.ready]
    missing = [c for c in cards if not c.readiness.ready]
    summary = (
        f"{len(ready)} of {len(cards)} views of this company can be built from what is "
        f"connected today."
    )
    if missing:
        summary += " " + ", ".join(c.label for c in missing) + " need more connected."

    return GeneralTwin(
        window_days=model.window_days,
        people=len(model.people),
        processes=len(model.processes),
        events=model.total_events,
        summary=summary,
        cards=cards,
    )
