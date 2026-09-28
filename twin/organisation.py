"""A living model of how work actually moves through a company (digital twin).

Built from the event log rather than an org chart, so it reflects who really does what, not
who is supposed to. Leaders use it to ask what happens if something changes, before they
change it.

Everything here is measured. Where the model has to assume something to answer a question,
the assumption is returned alongside the answer so nobody mistakes it for a fact.

People appear as stable pseudonyms rather than names. The boundary that keeps real identities
out of models keeps them out of this view too; the vault is the only place they live.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from core.db.pool import tenant_conn
from core.language import phrases
from core.language.format import Duration, duration

# How far back the model looks. Long enough to be representative, short enough to be current.
WINDOW_DAYS = 120
# A step this dependent on one person is a risk worth naming.
KEY_PERSON_SHARE = 0.6
# A wait cannot realistically stretch further than this from losing capacity alone.
MAX_SLOWDOWN = 5.0


def pseudonym(index: int) -> str:
    """Person A, Person B, ... Stable for a given model, and never a real name."""
    letters = ""
    n = index
    while True:
        letters = chr(ord("A") + n % 26) + letters
        n = n // 26 - 1
        if n < 0:
            break
    return f"Person {letters}"


# ---------------------------------------------------------------- the model
class StepRole(BaseModel):
    process_id: str
    process_name: str
    step: str
    verb: str
    events: int
    share: float = Field(description="Fraction of this step this person handles")
    others: int = Field(description="How many other people have done this step")


class PersonModel(BaseModel):
    token: str
    label: str
    events: int
    processes: list[str] = Field(default_factory=list)
    roles: list[StepRole] = Field(default_factory=list)

    @property
    def sole_owner_of(self) -> list[StepRole]:
        return [r for r in self.roles if r.others == 0]


class StepLoad(BaseModel):
    verb: str
    label: str
    events: int
    people: int
    per_week: float
    wait: Duration | None = None
    top_share: float = 0.0


class ProcessModel(BaseModel):
    id: str
    name: str
    cases: int
    people: int
    steps: list[StepLoad] = Field(default_factory=list)
    cycle: Duration
    slowest_verb: str = ""


class Risk(BaseModel):
    kind: Literal["key_person", "single_point", "concentration"]
    person: str
    process_name: str
    step: str
    share: float
    text: str


class OrgModel(BaseModel):
    window_days: int
    people: list[PersonModel] = Field(default_factory=list)
    processes: list[ProcessModel] = Field(default_factory=list)
    external_parties: int = 0
    total_events: int = 0
    risks: list[Risk] = Field(default_factory=list)


@dataclass
class _Raw:
    per_step: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))
    per_person_step: dict[tuple[str, str, str], int] = field(
        default_factory=lambda: defaultdict(int)
    )
    per_person: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    cases: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    externals: set[str] = field(default_factory=set)


async def _gather(tenant_id: str, since: datetime) -> _Raw:
    raw = _Raw()
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT actor, verb, objects FROM event_log WHERE tenant_id=$1 AND ts >= $2",
            tenant_id,
            since,
        )
    for row in rows:
        actor = row["actor"]
        actor = json.loads(actor) if isinstance(actor, str) else actor
        objects = row["objects"]
        objects = json.loads(objects) if isinstance(objects, str) else objects
        token = str(actor.get("token", "unknown"))
        verb = str(row["verb"])

        for obj in objects:
            kind = str(obj.get("object_type", ""))
            if kind in {"doc", ""}:
                continue
            raw.per_step[(kind, verb)] += 1
            raw.per_person_step[(token, kind, verb)] += 1
            raw.cases[kind].add(str(obj.get("object_id", "")))
        raw.per_person[token] += 1
        if token.startswith("<ORG_"):
            raw.externals.add(token)
    return raw


async def build_model(tenant_id: str, window_days: int = WINDOW_DAYS) -> OrgModel:
    """Read the company's own record and assemble the model."""
    from core.processes import list_processes

    since = datetime.now(tz=UTC) - timedelta(days=window_days)
    raw = await _gather(tenant_id, since)
    processes = await list_processes(tenant_id)
    by_id = {p.id: p for p in processes}

    # Stable pseudonyms: busiest first, so Person A is the one who shows up most.
    people_tokens = sorted(
        (t for t in raw.per_person if not t.startswith("<ORG_")),
        key=lambda t: (-raw.per_person[t], t),
    )
    labels = {token: pseudonym(i) for i, token in enumerate(people_tokens)}

    people: list[PersonModel] = []
    for token in people_tokens:
        roles: list[StepRole] = []
        touched: set[str] = set()
        for (person, process_id, verb), count in raw.per_person_step.items():
            if person != token or process_id not in by_id:
                continue
            total = raw.per_step[(process_id, verb)]
            others = len(
                {
                    p
                    for (p, pid, v) in raw.per_person_step
                    if pid == process_id and v == verb and p != token
                }
            )
            roles.append(
                StepRole(
                    process_id=process_id,
                    process_name=by_id[process_id].name,
                    step=phrases.step_label(verb),
                    verb=verb,
                    events=count,
                    share=round(count / total, 3) if total else 0.0,
                    others=others,
                )
            )
            touched.add(by_id[process_id].name)
        roles.sort(key=lambda r: -r.share)
        people.append(
            PersonModel(
                token=token,
                label=labels[token],
                events=raw.per_person[token],
                processes=sorted(touched),
                roles=roles,
            )
        )

    weeks = max(window_days / 7.0, 1.0)
    models: list[ProcessModel] = []
    for process in processes:
        loads: list[StepLoad] = []
        for verb, events in sorted(
            ((v, c) for (pid, v), c in raw.per_step.items() if pid == process.id),
            key=lambda x: -x[1],
        ):
            shares = [
                c / events
                for (p, pid, v), c in raw.per_person_step.items()
                if pid == process.id and v == verb and events
            ]
            people_count = len(
                [p for (p, pid, v) in raw.per_person_step if pid == process.id and v == verb]
            )
            loads.append(
                StepLoad(
                    verb=verb,
                    label=phrases.step_label(verb),
                    events=events,
                    people=people_count,
                    per_week=round(events / weeks, 2),
                    top_share=round(max(shares), 3) if shares else 0.0,
                )
            )
        models.append(
            ProcessModel(
                id=process.id,
                name=process.name,
                cases=len(raw.cases.get(process.id, set())),
                people=len({p for (p, pid, _) in raw.per_person_step if pid == process.id}),
                steps=loads,
                cycle=process.total_duration,
                slowest_verb="",
            )
        )

    risks: list[Risk] = []
    for member in people:
        for role in member.roles:
            if role.others == 0 and role.events >= 3:
                risks.append(
                    Risk(
                        kind="single_point",
                        person=member.label,
                        process_name=role.process_name,
                        step=role.step,
                        share=role.share,
                        text=(
                            f"{member.label} is the only person who has done "
                            f"{role.step.lower()} in {role.process_name}."
                        ),
                    )
                )
            elif role.share >= KEY_PERSON_SHARE and role.events >= 5:
                risks.append(
                    Risk(
                        kind="key_person",
                        person=member.label,
                        process_name=role.process_name,
                        step=role.step,
                        share=role.share,
                        text=(
                            f"{member.label} handles {round(role.share * 100)}% of "
                            f"{role.step.lower()} in {role.process_name}."
                        ),
                    )
                )
    risks.sort(key=lambda r: (r.kind != "single_point", -r.share))

    return OrgModel(
        window_days=window_days,
        people=people,
        processes=models,
        external_parties=len(raw.externals),
        total_events=sum(raw.per_person.values()),
        risks=risks[:8],
    )


# ---------------------------------------------------------------- what if
class Effect(BaseModel):
    process_id: str
    process_name: str
    step: str
    severity: Literal["stops", "slower", "fine"]
    text: str
    before: Duration | None = None
    after: Duration | None = None


class Scenario(BaseModel):
    kind: str
    title: str
    summary: str
    effects: list[Effect] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    cover: list[str] = Field(default_factory=list)


def _slower_by(share: float) -> float:
    """Losing a share of the people doing a step stretches how long it takes.

    Work that took one person a day takes two people half a day, so removing capacity
    multiplies the wait by 1/(1-share). Capped, because past a point a team reorganises
    rather than simply queueing forever.
    """
    if share >= 0.999:
        return math.inf
    return min(1 / (1 - share), MAX_SLOWDOWN)


def person_leaves(model: OrgModel, token: str) -> Scenario:
    person = next((p for p in model.people if p.token == token or p.label == token), None)
    if person is None:
        return Scenario(
            kind="person_leaves",
            title="Unknown person",
            summary="Nobody by that name shows up in the last few months of work.",
        )

    effects: list[Effect] = []
    cover: set[str] = set()
    for role in person.roles:
        process = next((p for p in model.processes if p.id == role.process_id), None)
        if process is None:
            continue
        if role.others == 0:
            effects.append(
                Effect(
                    process_id=role.process_id,
                    process_name=role.process_name,
                    step=role.step,
                    severity="stops",
                    text=(
                        f"{role.step} would stop. Nobody else has done it in the last "
                        f"{model.window_days} days."
                    ),
                )
            )
            continue

        factor = _slower_by(role.share)
        if factor <= 1.05:
            continue
        before = process.cycle
        after = duration(before.seconds * (1 + (factor - 1) * role.share))
        effects.append(
            Effect(
                process_id=role.process_id,
                process_name=role.process_name,
                step=role.step,
                severity="slower",
                text=(
                    f"{role.step} would slow down. {person.label} does "
                    f"{round(role.share * 100)}% of it, and {role.others} "
                    f"{'other person has' if role.others == 1 else 'others have'} done it before."
                ),
                before=before,
                after=after,
            )
        )
        for other in model.people:
            if other.token == person.token:
                continue
            if any(r.verb == role.verb and r.process_id == role.process_id for r in other.roles):
                cover.add(other.label)

    stops = [e for e in effects if e.severity == "stops"]
    if not effects:
        summary = (
            f"{person.label} leaving would not stall anything. Everything they touch is "
            "shared with other people."
        )
    elif stops:
        names = ", ".join(sorted({e.step.lower() for e in stops}))
        summary = (
            f"{person.label} leaving would stop {names}. Nobody else has done that work "
            f"in the last {model.window_days} days."
        )
    else:
        summary = (
            f"{person.label} leaving would slow down {len(effects)} "
            f"{'step' if len(effects) == 1 else 'steps'}, but nothing would stop."
        )

    return Scenario(
        kind="person_leaves",
        title=f"If {person.label} leaves",
        summary=summary,
        effects=sorted(effects, key=lambda e: e.severity != "stops"),
        assumptions=[
            f"Based on what actually happened in the last {model.window_days} days.",
            "Assumes nobody new is hired and the work still has to be done.",
        ],
        cover=sorted(cover),
    )


def demand_changes(model: OrgModel, process_id: str, multiplier: float) -> Scenario:
    process = next((p for p in model.processes if p.id == process_id), None)
    if process is None:
        return Scenario(
            kind="demand_changes",
            title="Unknown work",
            summary="That way of working is not in the model.",
        )

    direction = "more" if multiplier > 1 else "less"
    effects: list[Effect] = []
    for step in process.steps:
        needed = step.per_week * multiplier
        if step.people == 0:
            continue
        per_person = step.per_week / step.people
        people_needed = math.ceil(needed / per_person) if per_person > 0 else step.people
        severity: Literal["stops", "slower", "fine"] = (
            "slower" if people_needed > step.people else "fine"
        )
        if multiplier > 1 and step.top_share >= KEY_PERSON_SHARE:
            severity = "slower"
        effects.append(
            Effect(
                process_id=process.id,
                process_name=process.name,
                step=step.label,
                severity=severity,
                text=(
                    f"{step.label} goes from {step.per_week:.0f} to {needed:.0f} a week"
                    + (
                        f". {step.people} "
                        f"{'person handles' if step.people == 1 else 'people handle'} that today"
                        f", and at the same pace it would take {people_needed}."
                        if severity != "fine"
                        else f", which the {step.people} doing it today already cover."
                    )
                ),
            )
        )

    pressure = [e for e in effects if e.severity != "fine"]
    if multiplier <= 1:
        summary = (
            f"At {multiplier:g} times the volume, nothing is under pressure. "
            f"{process.name} has room."
        )
    elif pressure:
        first = pressure[0]
        summary = (
            f"At {multiplier:g} times the work, {first.step.lower()} is where it would bite first. "
            f"{len(pressure)} of {len(effects)} steps would need more hands."
        )
    else:
        summary = (
            f"At {multiplier:g} times the work, {process.name} would keep up with the people "
            "already doing it."
        )

    return Scenario(
        kind="demand_changes",
        title=f"If {direction} work comes in",
        summary=summary,
        effects=effects,
        assumptions=[
            f"Based on the last {model.window_days} days of real volume.",
            "Assumes each person keeps working at the pace they do now.",
            "Assumes the work arrives steadily rather than all at once.",
        ],
    )


def process_changes(
    model: OrgModel,
    process_id: str,
    detail_waits: list[tuple[str, str, float]],
    remove_step: str | None = None,
    speed_up_percent: float = 0.0,
) -> Scenario:
    """Take a step out, or cut one wait, and see what the whole thing becomes.

    `detail_waits` is (from_step, to_step, seconds) as measured, so the arithmetic is done
    against what really happens rather than against an estimate.
    """
    process = next((p for p in model.processes if p.id == process_id), None)
    if process is None or not detail_waits:
        return Scenario(
            kind="process_changes",
            title="Unknown work",
            summary="That way of working is not in the model yet.",
        )

    total_before = sum(seconds for _, _, seconds in detail_waits)
    effects: list[Effect] = []
    kept: list[tuple[str, str, float]] = []

    for from_step, to_step, seconds in detail_waits:
        removed = remove_step is not None and remove_step.lower() in {
            from_step.lower(),
            to_step.lower(),
        }
        if removed:
            effects.append(
                Effect(
                    process_id=process.id,
                    process_name=process.name,
                    step=to_step,
                    severity="fine",
                    text=f"The wait before {to_step.lower()} disappears.",
                    before=duration(seconds),
                    after=duration(0),
                )
            )
            continue

        if speed_up_percent > 0 and seconds == max(s for _, _, s in detail_waits):
            faster = seconds * (1 - speed_up_percent / 100)
            effects.append(
                Effect(
                    process_id=process.id,
                    process_name=process.name,
                    step=to_step,
                    severity="fine",
                    text=(
                        f"The longest wait, before {to_step.lower()}, is cut by "
                        f"{speed_up_percent:g}%."
                    ),
                    before=duration(seconds),
                    after=duration(faster),
                )
            )
            kept.append((from_step, to_step, faster))
            continue

        kept.append((from_step, to_step, seconds))

    total_after = sum(seconds for _, _, seconds in kept)
    saved = total_before - total_after

    if not effects:
        summary = "Nothing changes. Pick a step to remove, or shorten the longest wait."
    elif saved <= 0:
        summary = f"{process.name} would take about the same time."
    else:
        share = round(saved / total_before * 100) if total_before else 0
        summary = (
            f"{process.name} would go from {duration(total_before).text} to "
            f"{duration(total_after).text}, about {share}% faster."
        )
        new_slowest = max(kept, key=lambda w: w[2], default=None)
        if new_slowest:
            effects.append(
                Effect(
                    process_id=process.id,
                    process_name=process.name,
                    step=new_slowest[1],
                    severity="slower",
                    text=(
                        f"The wait before {new_slowest[1].lower()} becomes the longest one, "
                        f"at {duration(new_slowest[2]).text}."
                    ),
                )
            )

    return Scenario(
        kind="process_changes",
        title=f"If {process.name.lower()} changes",
        summary=summary,
        effects=effects,
        assumptions=[
            "Assumes the other steps carry on taking as long as they do today.",
            "Assumes removing a step does not push its work onto another one.",
        ],
    )
