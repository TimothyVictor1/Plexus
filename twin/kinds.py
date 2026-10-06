"""The twins a company can look at, and what each of them needs to exist.

One company is not one model. The same event log answers different questions depending on who
is asking: how work moves, where money sits, who knows what, which clients and projects are
healthy. Those are separate twins over shared evidence, not one twin with tabs.

A twin declares what it needs. If a company has not connected the tools that would feed it,
the twin says so by name instead of rendering an empty screen — "no code tool is connected"
is a true statement about that company, and a reason to connect one. A twin that quietly shows
nothing teaches a person that the product is broken.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class TwinId(StrEnum):
    general = "general"
    operational = "operational"
    financial = "financial"
    people = "people"
    business = "business"
    technical = "technical"


class Readiness(BaseModel):
    """Whether a twin can be built for this company, and what is missing if not."""

    ready: bool
    reason: str = ""
    needs: list[str] = Field(default_factory=list)


class TwinKind(BaseModel):
    id: TwinId
    label: str
    blurb: str
    # What has to be in the event log for this twin to mean anything. Checked against the
    # company's own data, never assumed.
    requires: list[str] = Field(default_factory=list)


KINDS: list[TwinKind] = [
    TwinKind(
        id=TwinId.general,
        label="The whole company",
        blurb="Everything at once: how work moves, where money sits, who knows what.",
    ),
    TwinKind(
        id=TwinId.operational,
        label="How work moves",
        blurb="The ways work gets done, how long each step takes, and where it waits.",
        requires=["events"],
    ),
    TwinKind(
        id=TwinId.financial,
        label="Where money sits",
        blurb="What money is moving through the work, and how long it waits on the way.",
        requires=["amounts"],
    ),
    TwinKind(
        id=TwinId.people,
        label="Who knows what",
        blurb="What each person actually does, what rests only on them, and how to hand it over.",
        requires=["events"],
    ),
    TwinKind(
        id=TwinId.business,
        label="Clients and projects",
        blurb="Which clients and projects are moving, and which have gone quiet.",
        requires=["organisations"],
    ),
    TwinKind(
        id=TwinId.technical,
        label="How software gets built",
        blurb="How changes reach production, what review costs, and what rests on one engineer.",
        requires=["code"],
    ),
]

BY_ID = {kind.id: kind for kind in KINDS}
