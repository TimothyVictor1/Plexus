"""Deterministic recognisers for the PII Boundary (spec 06).

Swedish-specific patterns live here rather than in Presidio, because the stock Presidio images
carry no Swedish NLP model. Presidio is layered on top additively by boundary.py when it is
reachable; these local recognisers always run, so the boundary never silently degrades.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    entity_type: str
    value: str
    priority: int
    score: float = 1.0


@dataclass(frozen=True)
class Recogniser:
    entity_type: str
    pattern: re.Pattern[str]
    priority: int
    validate: Callable[[str], bool] | None = None
    score: float = 0.9


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        n = int(ch)
        if i % 2 == parity:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _plausible_date(six: str) -> bool:
    month, day = int(six[2:4]), int(six[4:6])
    return 1 <= month <= 12 and 1 <= day <= 31


def valid_personnummer(raw: str) -> bool:
    """YYMMDD-NNNN or YYYYMMDD-NNNN, Luhn over the 10 significant digits."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10 or not _plausible_date(digits[:6]):
        return False
    return _luhn_ok(digits)


def valid_orgnr(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        return False
    # Swedish org numbers have a third digit of 2 or more; that is what separates them from
    # a personnummer, whose third digit is a month.
    return int(digits[2]) >= 2 and _luhn_ok(digits)


RECOGNISERS: tuple[Recogniser, ...] = (
    Recogniser("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"), 10, score=1.0),
    Recogniser("IBAN", re.compile(r"\bSE\d{2}(?:\s?\d{4}){5}\b"), 20, score=1.0),
    Recogniser(
        "PNR",
        re.compile(r"\b(?:19|20)?\d{6}[-+]\d{4}\b"),
        30,
        validate=valid_personnummer,
        score=1.0,
    ),
    Recogniser("ORGNR", re.compile(r"\b(?:16)?\d{6}-\d{4}\b"), 40, validate=valid_orgnr, score=1.0),
    Recogniser("PHONE", re.compile(r"(?:\+46|0)[\s-]?7[\s-]?\d(?:[\s-]?\d){7}\b"), 50),
    Recogniser("BANKGIRO", re.compile(r"\b\d{3,4}-\d{4}\b"), 60, score=0.7),
    Recogniser(
        "ADDRESS",
        re.compile(
            r"\b[A-ZÅÄÖ][a-zåäöé]+(?:gatan|vägen|gränd|gränden|torget|backen|stigen|allén)"
            r"\s+\d+[A-Za-z]?\b"
        ),
        70,
    ),
)


def find_spans(text: str, extra_names: frozenset[str] = frozenset()) -> list[Span]:
    """All recogniser hits, overlaps resolved by earliest start then highest priority."""
    spans: list[Span] = []
    for rec in RECOGNISERS:
        for match in rec.pattern.finditer(text):
            raw = match.group(0)
            if rec.validate is not None and not rec.validate(raw):
                continue
            spans.append(
                Span(match.start(), match.end(), rec.entity_type, raw, rec.priority, rec.score)
            )
    for name in extra_names:
        start = text.find(name)
        while start != -1:
            spans.append(Span(start, start + len(name), "PERSON", name, 5, 0.85))
            start = text.find(name, start + 1)

    spans.sort(key=lambda s: (s.start, s.priority, -(s.end - s.start)))
    kept: list[Span] = []
    last_end = -1
    for span in spans:
        if span.start >= last_end:
            kept.append(span)
            last_end = span.end
    return kept
