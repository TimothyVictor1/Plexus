"""The surveyor: the first agent, and the only one that looks at raw shape.

It measures and does not interpret. Every later judgement rests on these counts, so this step
contains no model call, no heuristics about meaning, and no field names it hopes to find — it
walks whatever arrives and reports what is there.

Read-only by construction: it takes items that have already passed the PII Boundary and
returns numbers. It cannot reach an adapter, so it cannot write to one.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agents.onboard.profile import FieldProfile

# A payload can nest arbitrarily; past a few levels it is structure, not data, and walking
# forever on a pathological document helps nobody.
MAX_DEPTH = 4
MAX_EXAMPLES = 5
# Enough to be representative without reading a company's entire history to describe it.
DEFAULT_SAMPLE = 400


@dataclass
class _Stat:
    seen: int = 0
    filled: int = 0
    numeric: int = 0
    distinct: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)
    # Values that parse as a date, and values that look like a currency code. Counted here
    # because counting is cheap and the classifier should not re-walk the data to find out.
    datelike: int = 0
    codelike: int = 0

    def add(self, value: Any) -> None:
        self.seen += 1
        if value is None or value == "":
            return
        self.filled += 1

        if isinstance(value, bool):
            text = str(value)
        elif isinstance(value, int | float):
            self.numeric += 1
            text = f"{value}"
        else:
            text = str(value)
            if _numeric(text):
                self.numeric += 1
            if _datelike(text):
                self.datelike += 1
            if _codelike(text):
                self.codelike += 1

        if len(self.distinct) < 5000:
            self.distinct.add(text[:80])
        if len(self.examples) < MAX_EXAMPLES and text not in self.examples:
            self.examples.append(text[:80])


def _numeric(text: str) -> bool:
    try:
        float(text.replace(",", "").replace(" ", ""))
    except ValueError:
        return False
    return True


def _datelike(text: str) -> bool:
    if len(text) < 8 or len(text) > 40:
        return False
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _codelike(text: str) -> bool:
    """Three upper-case letters, the shape of a currency code. Shape only; no list of codes.

    A list would be a different way of conforming to data we happen to have seen, and a company
    may well use a code we have never heard of.
    """
    return len(text) == 3 and text.isalpha() and text.isupper()


def _walk(payload: Any, prefix: str, out: dict[str, Any], depth: int = 0) -> None:
    """Flatten a payload to dotted paths. A list is sampled at its first element: the shape of
    a line item is what matters, not how many there happen to be."""
    if depth > MAX_DEPTH:
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            _walk(value, f"{prefix}.{key}" if prefix else str(key), out, depth + 1)
        return
    if isinstance(payload, list):
        if payload:
            _walk(payload[0], f"{prefix}[]", out, depth + 1)
        return
    out[prefix] = payload


def survey(
    source_id: str, payloads: list[dict[str, Any]], *, sample: int = DEFAULT_SAMPLE
) -> list[FieldProfile]:
    """Measure one source's payloads and return a profile per field, kind still unknown.

    Deciding what the fields mean is the classifier's job. Keeping the two apart means the
    measurements can be checked on their own, and a wrong interpretation never hides inside a
    wrong count.
    """
    stats: dict[str, _Stat] = defaultdict(_Stat)
    looked_at = 0

    for payload in payloads[:sample]:
        flat: dict[str, Any] = {}
        _walk(payload, "", flat)
        looked_at += 1
        for path, value in flat.items():
            stats[path].add(value)
        # A field absent from this payload is still a field that was offered and not filled.
        for path in stats:
            if path not in flat:
                stats[path].seen += 1

    profiles: list[FieldProfile] = []
    for path, stat in sorted(stats.items()):
        filled = max(stat.filled, 1)
        profiles.append(
            FieldProfile(
                source_id=source_id,
                path=path,
                seen=stat.seen,
                filled=stat.filled,
                distinct=len(stat.distinct),
                numeric_share=round(stat.numeric / filled, 3),
                examples=list(stat.examples),
                evidence=[
                    f"Seen in {stat.filled} of {stat.seen} records from {source_id}.",
                    f"{len(stat.distinct)} distinct values; "
                    f"{round(stat.numeric / filled * 100)}% numeric, "
                    f"{round(stat.datelike / filled * 100)}% parse as a date, "
                    f"{round(stat.codelike / filled * 100)}% look like a currency code.",
                ],
            )
        )
    return profiles


def counts(source_id: str, payloads: list[dict[str, Any]]) -> dict[str, int]:
    """A quick shape report, for the crew's own log."""
    profiles = survey(source_id, payloads)
    return {"records": len(payloads), "fields": len(profiles)}
