"""The things a company talks about — its projects, its people, the outside parties it works
with — and what has recently happened to each.

Document search answers "what was said". It cannot answer "where has the Acme work got to",
because that is not written down anywhere: it is the shape of a hundred events that mention
the same thing. The event log already holds those relationships — every event names the
objects it touched and the person who did it — so the connections can be read straight out of
it without a second database standing by.

Nothing here matches on a field name. An entity is whatever the events point at, and a person
is whoever the events are attributed to, so a company that calls its work something unfamiliar
is understood exactly as well as one that does not.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.db.pool import tenant_conn
from core.language import phrases

# Enough recent activity to say where something stands, without reciting its whole history.
TIMELINE = 8
MAX_ENTITIES = 4


@dataclass
class Moment:
    ts: datetime
    verb: str
    actor: str


@dataclass
class Entity:
    """One thing the company's records are about, and where it has got to."""

    key: str
    kind: str
    label: str
    events: int
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    people: list[str] = field(default_factory=list)
    timeline: list[Moment] = field(default_factory=list)

    def sentence(self, *, now: datetime | None = None) -> str:
        """Where this stands, in one line somebody can read."""
        if not self.timeline:
            return f"{self.label}: nothing recorded."
        latest = self.timeline[0]
        said = phrases.step_label(latest.verb).lower()
        when = (
            phrases.ago(latest.ts, now) if hasattr(phrases, "ago") else latest.ts.date().isoformat()
        )
        who = f" by {latest.actor}" if latest.actor else ""
        line = f"{self.label}: last thing to happen was {said}{who}, {when}."
        if self.people:
            n = len(self.people)
            line += (
                f" {n} {'person has' if n == 1 else 'people have'} touched it: "
                f"{', '.join(self.people[:4])}."
            )
        return line


def _j(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def _people_labels(tenant_id: str) -> dict[str, str]:
    """Tokens to the pseudonyms the rest of the product shows, so Ask names people the same
    way the twin does rather than inventing a second vocabulary."""
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "SELECT actor::jsonb->>'token' AS token, count(*) AS n FROM event_log"
            " WHERE tenant_id=$1 GROUP BY 1 ORDER BY n DESC",
            tenant_id,
        )
    from twin.organisation import pseudonym

    return {str(r["token"]): pseudonym(i) for i, r in enumerate(rows) if r["token"]}


# Identifiers survive whole: "expenses-034" is one name, and splitting it on the hyphen turns
# a question about one expense into a question about every expense.
IDENTIFIER = re.compile(r"[A-Za-z0-9ÅÄÖåäö]+(?:[-_][A-Za-z0-9]+)+")


def names_in(question: str) -> list[str]:
    """Things in a question that look like the name of something, longest first."""
    return sorted(set(IDENTIFIER.findall(question)), key=len, reverse=True)


async def find_entities(
    tenant_id: str, terms: list[str], question: str = "", limit: int = MAX_ENTITIES
) -> list[Entity]:
    """Entities whose identifier mentions what the question named.

    Whole identifiers are preferred over loose words. Asking about one expense must not be
    answered about a different one that happens to share a prefix: a near miss here reads as
    the product being confidently wrong, not as a search result.
    """
    exact = names_in(question)
    if not exact and not terms:
        return []

    pattern = "|".join(re.escape(e) for e in exact) if exact else "|".join(terms)
    exact_pattern = "|".join(re.escape(e) for e in exact) if exact else "(?!)"
    async with tenant_conn(tenant_id) as conn:
        rows = await conn.fetch(
            "WITH touched AS ("
            "  SELECT o->>'object_id' AS key, o->>'object_type' AS kind,"
            "         e.ts, e.verb, e.actor::jsonb->>'token' AS actor"
            "  FROM event_log e, jsonb_array_elements(e.objects::jsonb) o"
            "  WHERE e.tenant_id=$1 AND o->>'object_type' <> 'doc'"
            ")"
            " SELECT key, kind, count(*) AS events,"
            "        min(ts) AS first_seen, max(ts) AS last_seen"
            " FROM touched WHERE key ~* $2"
            " GROUP BY key, kind"
            " ORDER BY (key ~* $3) DESC, max(ts) DESC LIMIT $4",
            tenant_id,
            pattern,
            exact_pattern,
            limit,
        )

        labels = await _people_labels(tenant_id)
        entities: list[Entity] = []
        for row in rows:
            moments = await conn.fetch(
                "SELECT e.ts, e.verb, e.actor::jsonb->>'token' AS actor"
                " FROM event_log e, jsonb_array_elements(e.objects::jsonb) o"
                " WHERE e.tenant_id=$1 AND o->>'object_id' = $2"
                " ORDER BY e.ts DESC LIMIT $3",
                tenant_id,
                row["key"],
                TIMELINE,
            )
            timeline = [
                Moment(ts=m["ts"], verb=m["verb"], actor=labels.get(str(m["actor"]), ""))
                for m in moments
            ]
            people: list[str] = []
            for moment in timeline:
                if moment.actor and moment.actor not in people:
                    people.append(moment.actor)
            entities.append(
                Entity(
                    key=str(row["key"]),
                    kind=str(row["kind"]),
                    label=str(row["key"]),
                    events=int(row["events"]),
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                    people=people,
                    timeline=timeline,
                )
            )
    return entities


async def contributions(tenant_id: str, who: str) -> list[str]:
    """What one person has actually done, for questions about a named colleague.

    Read off the record rather than a job description, which is the only version that is true
    after the first month.
    """
    from twin.organisation import build_model
    from twin.people import build as build_people

    twin = build_people(await build_model(tenant_id))
    wanted = who.strip().lower()
    for person in twin.people:
        if person.label.lower() == wanted or person.token.lower() == wanted:
            lines = [person.summary]
            lines += [f"{r.step} in {r.process_name}, {r.events} times" for r in person.does[:6]]
            return lines
    return []


def as_notes(entities: list[Entity]) -> str:
    """The entity findings, as the lines the model is allowed to answer from."""
    if not entities:
        return ""
    out = ["What the records show about the things you named:"]
    for entity in entities:
        out.append(f"- {entity.sentence()}")
        for moment in entity.timeline[:4]:
            who = f" ({moment.actor})" if moment.actor else ""
            out.append(f"    {moment.ts.date().isoformat()} {moment.verb}{who}")
    return "\n".join(out)
