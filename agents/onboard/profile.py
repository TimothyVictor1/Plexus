"""What Plexus learned about one company's own data.

Nothing in the product may name a field. A company does not call its money `amount` because
Plexus would like it to; it calls it `total_incl_vat`, or `belopp`, or nests it inside a line
item. The moment a feature reads a key by name it works for whoever the fixtures were modelled
on and quietly fails for everyone else.

So field names live here, discovered per tenant, and the rest of the product asks this profile
instead of guessing. A profile is a record of evidence, not a configuration: every judgement
carries what it was based on and how sure it is, so a wrong one can be seen rather than found
later in a number nobody can explain.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class FieldKind(StrEnum):
    """What a field turned out to be, in terms the rest of the product can use."""

    money = "money"
    currency = "currency"
    quantity = "quantity"
    timestamp = "timestamp"
    identity = "identity"
    reference = "reference"
    status = "status"
    text = "text"
    unknown = "unknown"


class FieldProfile(BaseModel):
    source_id: str
    path: str = Field(description="Dotted path into the item's structured payload")
    kind: FieldKind = FieldKind.unknown
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Why this was decided, in sentences a person can check. An unexplained judgement is
    # indistinguishable from a guess, and this one ends up in financial figures.
    evidence: list[str] = Field(default_factory=list)

    # Shape, measured rather than assumed.
    seen: int = 0
    filled: int = 0
    distinct: int = 0
    numeric_share: float = 0.0
    examples: list[str] = Field(default_factory=list)

    # Money only. Never defaulted: a figure without a known unit is not a figure.
    currency_path: str | None = None
    currencies: list[str] = Field(default_factory=list)

    @property
    def fill_rate(self) -> float:
        return self.filled / self.seen if self.seen else 0.0

    @property
    def usable(self) -> bool:
        """Confident enough, and present often enough, to compute with."""
        return self.confidence >= 0.6 and self.fill_rate >= 0.2


class DataProfile(BaseModel):
    """One company's shape, as discovered. Versioned, because data changes and so does this."""

    tenant_id: str
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    fields: list[FieldProfile] = Field(default_factory=list)
    # What the crew could not settle. Carried deliberately: an unanswered question is worth
    # more than a confident wrong answer, and the operator can resolve it later.
    open_questions: list[str] = Field(default_factory=list)

    def of_kind(self, kind: FieldKind, *, usable_only: bool = True) -> list[FieldProfile]:
        return [f for f in self.fields if f.kind is kind and (f.usable if usable_only else True)]

    def money_fields(self, source_id: str | None = None) -> list[FieldProfile]:
        """Where this company keeps its money, if anywhere.

        An empty list is a real answer and the product must be able to say it: plenty of work
        carries no figures at all, and inventing one is worse than reporting none.
        """
        found = self.of_kind(FieldKind.money)
        return [f for f in found if source_id is None or f.source_id == source_id]

    def currencies(self) -> list[str]:
        seen: list[str] = []
        for field in self.money_fields():
            for code in field.currencies:
                if code and code not in seen:
                    seen.append(code)
        return sorted(seen)
