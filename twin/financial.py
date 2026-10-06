"""Where a company's money actually sits, and how long it waits there.

Not an accounting system and not trying to be one. The ledger of record is whatever the company
already uses; this answers a different question that no accounting system does — not *how much*
but *how long*, and *behind which step*. Money is rarely lost. It waits, behind a person who has
not sent something.

Every figure traces to records the company itself produced, in the currency those records
carry. Nothing is converted between currencies and nothing is assumed about one: a company that
invoices in three currencies has three answers, and showing one blended number would be a lie
with a decimal point on it.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from core.language.format import Duration
from twin.organisation import OrgModel, ProcessModel


class MoneyAtRest(BaseModel):
    process_id: str
    process_name: str
    currency: str
    total: float
    records: int
    # The step money waits behind, and for how long.
    waits_at: str = ""
    wait: Duration | None = None
    note: str = ""


class FinancialTwin(BaseModel):
    window_days: int
    currencies: list[str] = Field(default_factory=list)
    at_rest: list[MoneyAtRest] = Field(default_factory=list)
    # Processes that carry no figures at all. Named, because a blank screen looks like a fault.
    without_amounts: list[str] = Field(default_factory=list)
    summary: str = ""
    ready: bool = True
    reason: str = ""


def _slowest(process: ProcessModel) -> tuple[str, Duration | None]:
    """Where this work waits, as the mined process already determined."""
    return process.slowest_step, process.slowest_wait


def build(model: OrgModel) -> FinancialTwin:
    priced = [p for p in model.processes if p.money and p.currency]
    silent = [p.name for p in model.processes if not p.money]

    if not priced:
        return FinancialTwin(
            window_days=model.window_days,
            without_amounts=silent,
            ready=False,
            reason=(
                "None of this company's work carries amounts in its records"
                + (f" — {', '.join(silent)} carry none" if silent else "")
                + ". Connect the tool that holds invoices or expenses and this fills in."
            ),
        )

    at_rest: list[MoneyAtRest] = []
    for process in sorted(priced, key=lambda p: -p.money):
        step, wait = _slowest(process)
        note = (
            f"{process.money:,.0f} {process.currency} moved through this across "
            f"{process.money_events} records in {model.window_days} days."
        )
        if step and wait:
            note += f" The longest it waits is {wait.text}, at {step}."
        at_rest.append(
            MoneyAtRest(
                process_id=process.id,
                process_name=process.name,
                currency=process.currency,
                total=round(process.money, 2),
                records=process.money_events,
                waits_at=step,
                wait=wait,
                note=note,
            )
        )

    # Totals are per currency. Never summed across: that would invent an exchange rate.
    totals: dict[str, float] = defaultdict(float)
    for item in at_rest:
        totals[item.currency] += item.total
    parts = [f"{total:,.0f} {code}" for code, total in sorted(totals.items())]

    summary = f"{' and '.join(parts)} moved through this company's work in the last "
    summary += f"{model.window_days} days."
    worst = max(at_rest, key=lambda m: m.wait.seconds if m.wait else 0)
    if worst.wait:
        summary += f" The longest any of it waits is {worst.wait.text}, at {worst.waits_at}."
    if silent:
        summary += f" {', '.join(silent)} carry no amounts, so they are not counted."

    return FinancialTwin(
        window_days=model.window_days,
        currencies=sorted(totals),
        at_rest=at_rest,
        without_amounts=silent,
        summary=summary,
    )
