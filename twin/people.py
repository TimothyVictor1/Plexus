"""A twin of each person, so that what they know does not leave when they do.

Everything here is read off what someone actually did, never what a job title says they do.
The event log already attributes every action, so the question "what does this person do" has
an evidenced answer: which steps, how often, how much of each one is theirs, and which of them
nobody else has ever touched.

That last set is the handover. When somebody leaves, the person taking over does not need an
org chart — they need the list of things only the leaver has ever done, in the order they are
about to come up, with the records to read. This builds that list.

People are pseudonymous here as everywhere: Plexus holds a token, not a name. A company that
wants a real name against a twin resolves it at the edge, through the one code path allowed to
restore, and never in the model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.language.format import Duration
from twin.organisation import OrgModel, PersonModel, StepRole


class Handover(BaseModel):
    """One thing that has to pass from one person to another."""

    process_id: str
    process_name: str
    step: str
    events: int
    share: float
    others: int
    urgency: str = Field(description="only_them | mostly_them | shared")
    note: str


class PersonTwin(BaseModel):
    token: str
    label: str
    events: int
    processes: list[str] = Field(default_factory=list)
    # What they do, busiest first.
    does: list[StepRole] = Field(default_factory=list)
    # What would not survive their leaving, worst first.
    handover: list[Handover] = Field(default_factory=list)
    # Who already shares each piece of work, so a successor has somewhere to start.
    overlaps_with: list[str] = Field(default_factory=list)
    summary: str = ""


class PeopleTwin(BaseModel):
    window_days: int
    people: list[PersonTwin] = Field(default_factory=list)
    # Work that rests on exactly one person, across the whole company.
    only_one_person: int = 0
    summary: str = ""


def _urgency(role: StepRole) -> tuple[str, str]:
    if role.others == 0:
        return "only_them", (
            f"Nobody else has done {role.step} in {role.process_name}. This has to be taught, "
            "not handed over."
        )
    if role.share >= 0.8:
        who = "1 other person has" if role.others == 1 else f"{role.others} other people have"
        start = "That person is" if role.others == 1 else "Those people are"
        return "mostly_them", (
            f"They do {role.share * 100:.0f}% of {role.step} in {role.process_name}, and "
            f"{who} done it. {start} where to start."
        )
    return "shared", (
        f"{role.step} in {role.process_name} is already shared with "
        f"{role.others} other {'person' if role.others == 1 else 'people'}."
    )


def person_twin(model: OrgModel, person: PersonModel) -> PersonTwin:
    """One person, as their work describes them."""
    roles = sorted(person.roles, key=lambda r: -r.events)

    handover: list[Handover] = []
    for role in roles:
        urgency, note = _urgency(role)
        if urgency == "shared":
            continue
        handover.append(
            Handover(
                process_id=role.process_id,
                process_name=role.process_name,
                step=role.step,
                events=role.events,
                share=role.share,
                others=role.others,
                urgency=urgency,
                note=note,
            )
        )
    # Only-them first, then by how much of it is theirs: that is the order a successor meets it.
    handover.sort(key=lambda h: (h.urgency != "only_them", -h.share))

    # Anyone who has done any of the same steps is a place to start.
    overlaps: list[str] = []
    for other in model.people:
        if other.token == person.token:
            continue
        shared = {(r.process_id, r.step) for r in other.roles} & {
            (r.process_id, r.step) for r in roles
        }
        if shared:
            overlaps.append(other.label)

    alone = sum(1 for h in handover if h.urgency == "only_them")
    if alone:
        summary = (
            f"{person.label} is the only person who has done {alone} "
            f"{'thing' if alone == 1 else 'things'} in the last {model.window_days} days."
        )
    elif handover:
        summary = (
            f"{person.label} does most of {len(handover)} steps, but others have done them too."
        )
    else:
        summary = f"Everything {person.label} does is already shared with someone else."

    return PersonTwin(
        token=person.token,
        label=person.label,
        events=person.events,
        processes=sorted(person.processes),
        does=roles,
        handover=handover,
        overlaps_with=sorted(overlaps),
        summary=summary,
    )


def build(model: OrgModel) -> PeopleTwin:
    people = [person_twin(model, p) for p in model.people]
    alone = sum(1 for p in people for h in p.handover if h.urgency == "only_them")
    if not people:
        summary = "Nobody has done anything in the window, so there is nothing to describe yet."
    elif alone:
        summary = (
            f"{alone} {'step rests' if alone == 1 else 'steps rest'} on a single person. "
            "Those are the ones that do not survive a resignation."
        )
    else:
        summary = "Every step here has been done by more than one person."
    return PeopleTwin(
        window_days=model.window_days, people=people, only_one_person=alone, summary=summary
    )


def successor_brief(twin: PersonTwin) -> list[str]:
    """What to tell the person taking over, in the order it will come up.

    Deliberately plain sentences rather than a structure: this is read once, by someone new,
    who needs to know what lands on them on Monday.
    """
    lines = [twin.summary]
    for item in twin.handover:
        lines.append(item.note)
    if twin.overlaps_with:
        lines.append(
            "People who have done some of this before: " + ", ".join(twin.overlaps_with) + "."
        )
    return lines


__all__ = ["Duration", "Handover", "PeopleTwin", "PersonTwin", "build", "successor_brief"]
