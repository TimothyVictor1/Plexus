"""The classifier: decides what each measured field actually is.

Evidence first, model second, and the split is deliberate. Most fields are settled by what the
surveyor already counted — a column that is wholly numeric, carries two decimal places and sits
beside a column of three-letter codes is money whatever anyone calls it, in any language. That
judgement is reproducible, costs nothing, and can be checked line by line.

A model is asked only about the fields the evidence genuinely cannot settle, and it is asked
about tokenised samples, never raw records. It never overrules strong evidence; it breaks ties.
This matters because a company's profile decides financial figures: the same data must classify
the same way twice, and every answer has to be explainable afterwards.

Names are used as one weak signal among several, never alone. The failure being corrected here
was reading one hard-coded key; the fix is not to ban names but to stop trusting them on their
own, in one language.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from agents.onboard.profile import FieldKind, FieldProfile

# Lexical hints in several languages. A weak signal, deliberately: it can nudge an otherwise
# balanced decision and can never make one by itself. Extending this list makes Plexus better
# at a new market; forgetting one must not make it wrong, only less certain.
MONEY_WORDS = (
    "amount",
    "total",
    "sum",
    "price",
    "cost",
    "value",
    "gross",
    "net",
    "fee",
    "charge",
    "belopp",
    "betrag",
    "montant",
    "importe",
    "valore",
    "bedrag",
    "kwota",
    "soma",
)
TIME_WORDS = ("date", "time", "at", "on", "when", "datum", "fecha", "tid", "ts")
ID_WORDS = ("id", "key", "ref", "no", "number", "uuid", "nummer", "kod", "code")
STATUS_WORDS = ("status", "state", "stage", "phase", "stadium", "estado", "etat", "zustand")

# Two decimal places is how money is written almost everywhere, and almost never how a count is.
DECIMAL_MONEY = re.compile(r"^-?\d+[.,]\d{2}$")

Adjudicator = Callable[[list[FieldProfile]], Awaitable[dict[str, FieldKind]]]


def _words(path: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", path.lower()) if w]


def _hints(path: str, words: tuple[str, ...]) -> bool:
    parts = _words(path)
    return any(p == w or p.endswith(w) or p.startswith(w) for p in parts for w in words)


def _is_currency_column(field: FieldProfile) -> bool:
    """Every value a three-letter uppercase code. Shape, not a list of codes we know."""
    if not field.examples or field.distinct > 12:
        return False
    return all(len(e) == 3 and e.isalpha() and e.isupper() for e in field.examples)


def _sibling_currency(field: FieldProfile, all_fields: list[FieldProfile]) -> FieldProfile | None:
    """A column of three-letter uppercase codes beside this one is almost certainly its unit.

    Structural, not lexical: it finds a currency column whatever the company calls it, and it
    finds none when there is none rather than assuming the country.
    """
    parent = field.path.rsplit(".", 1)[0] if "." in field.path else ""
    for other in all_fields:
        if other.path == field.path or other.source_id != field.source_id:
            continue
        other_parent = other.path.rsplit(".", 1)[0] if "." in other.path else ""
        if other_parent != parent:
            continue
        if not other.examples:
            continue
        if _is_currency_column(other):
            return other
    return None


def _numeric_peers(field: FieldProfile, all_fields: list[FieldProfile]) -> int:
    """How many other numeric columns share this one's currency column.

    One amount beside one currency is unambiguous. Three numbers beside one currency is not:
    one of them is the money and the others are counts, and nothing structural says which.
    """
    parent = field.path.rsplit(".", 1)[0] if "." in field.path else ""
    peers = 0
    for other in all_fields:
        if other.path == field.path or other.source_id != field.source_id:
            continue
        other_parent = other.path.rsplit(".", 1)[0] if "." in other.path else ""
        if other_parent == parent and other.numeric_share >= 0.9:
            peers += 1
    return peers


def _looks_like_money(field: FieldProfile, currency: FieldProfile | None) -> tuple[float, str]:
    """How strongly the evidence says money, and why."""
    if field.numeric_share < 0.9:
        return 0.0, ""
    score, why = 0.35, "almost every value is a number"
    if currency is not None:
        score += 0.45
        why += f"; a column of currency codes sits beside it ({currency.path})"
    if any(DECIMAL_MONEY.match(e) for e in field.examples):
        score += 0.2
        why += "; values carry two decimal places"
    if _hints(field.path, MONEY_WORDS):
        score += 0.1
        why += "; the name reads like money in at least one language"
    return min(score, 0.98), why


def classify_one(field: FieldProfile, peers: list[FieldProfile]) -> FieldProfile:
    """Settle one field from evidence alone, or leave it unknown for the model to adjudicate."""
    filled = max(field.filled, 1)
    distinct_ratio = field.distinct / filled

    # Dates are the least ambiguous thing in any payload: either values parse or they do not.
    datelike = any("parse as a date" in e for e in field.evidence)
    date_share = 0.0
    for note in field.evidence:
        match = re.search(r"(\d+)% parse as a date", note)
        if match:
            date_share = int(match.group(1)) / 100
    if datelike and date_share >= 0.9:
        return field.model_copy(
            update={
                "kind": FieldKind.timestamp,
                "confidence": 0.95,
                "evidence": [*field.evidence, "Nearly every value parses as a date."],
            }
        )

    if _is_currency_column(field):
        return field.model_copy(
            update={
                "kind": FieldKind.currency,
                "confidence": 0.9,
                "currencies": sorted(set(field.examples)),
                "evidence": [
                    *field.evidence,
                    "Every value is a three-letter code, which is how a currency is written.",
                ],
            }
        )

    currency = _sibling_currency(field, peers)
    rivals = _numeric_peers(field, peers) if currency else 0
    money_score, money_why = _looks_like_money(field, currency)

    # One currency column cannot vouch for several numbers at once. Without a second signal
    # saying which of them is the money, this is exactly what the model is for.
    decisive = any(DECIMAL_MONEY.match(e) for e in field.examples) or _hints(
        field.path, MONEY_WORDS
    )
    contested = field.numeric_share >= 0.9 and currency is not None and rivals >= 1
    if contested and not decisive:
        return field.model_copy(
            update={
                "evidence": [
                    *field.evidence,
                    f"Numeric, and a currency column sits beside it, but {rivals} other "
                    "numeric columns sit beside the same one. Nothing here says which is the "
                    "money, so it is left unsettled rather than guessed.",
                ]
            }
        )
    if money_score >= 0.6:
        return field.model_copy(
            update={
                "kind": FieldKind.money,
                "confidence": round(money_score, 2),
                "currency_path": currency.path if currency else None,
                "currencies": sorted({e for e in (currency.examples if currency else [])}),
                "evidence": [*field.evidence, f"Read as money because {money_why}."],
            }
        )

    # A numeric column with no unit anywhere is a count, not a sum of money.
    if field.numeric_share >= 0.9:
        return field.model_copy(
            update={
                "kind": FieldKind.quantity,
                "confidence": 0.7,
                "evidence": [
                    *field.evidence,
                    "Numeric, but nothing nearby says what unit it is in, so it is counted "
                    "rather than valued.",
                ],
            }
        )

    # Nearly unique strings identify something; a short vocabulary describes a state.
    if field.filled >= 10 and distinct_ratio >= 0.9:
        kind = FieldKind.reference if _hints(field.path, ID_WORDS) else FieldKind.identity
        return field.model_copy(
            update={
                "kind": kind,
                "confidence": 0.75,
                "evidence": [*field.evidence, "Nearly every value is different."],
            }
        )
    if field.filled >= 10 and field.distinct <= 12 and distinct_ratio < 0.2:
        return field.model_copy(
            update={
                "kind": FieldKind.status,
                "confidence": 0.8 if _hints(field.path, STATUS_WORDS) else 0.65,
                "evidence": [
                    *field.evidence,
                    f"Only {field.distinct} different values ever appear, which is a short "
                    "vocabulary rather than data.",
                ],
            }
        )

    long_text = any(len(e) > 60 for e in field.examples)
    if long_text:
        return field.model_copy(
            update={
                "kind": FieldKind.text,
                "confidence": 0.7,
                "evidence": [*field.evidence, "Values are long enough to be prose."],
            }
        )

    return field.model_copy(
        update={"evidence": [*field.evidence, "The evidence does not settle what this is."]}
    )


async def classify(
    fields: list[FieldProfile], adjudicate: Adjudicator | None = None
) -> list[FieldProfile]:
    """Classify every field, asking the adjudicator only about the ones evidence cannot settle.

    The adjudicator is injected rather than imported so this can be tested, and run, without a
    model at all. With none supplied the unsettled fields stay unknown, which is the honest
    outcome: unknown is a usable answer and a guess is not.
    """
    settled = [classify_one(f, fields) for f in fields]
    unsure = [f for f in settled if f.kind is FieldKind.unknown]
    if not unsure or adjudicate is None:
        return settled

    verdicts = await adjudicate(unsure)
    out: list[FieldProfile] = []
    for field in settled:
        verdict = verdicts.get(field.path)
        if field.kind is FieldKind.unknown and verdict is not None:
            out.append(
                field.model_copy(
                    update={
                        # Capped below anything the evidence decides on its own: a judgement
                        # about meaning is never as solid as a measurement.
                        "kind": verdict,
                        "confidence": 0.55,
                        "evidence": [
                            *field.evidence,
                            "Settled by a model reading tokenised samples, because the "
                            "evidence alone was not enough.",
                        ],
                    }
                )
            )
        else:
            out.append(field)
    return out
