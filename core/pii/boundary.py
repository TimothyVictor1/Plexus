"""The PII Boundary (spec 06).

Every byte leaving an adapter passes through `tokenize`. `restore` is imported by exactly one
module, core/action/executor.py, and that is enforced by tests/architecture.

Tokens are format-preserving and stable per tenant: the same value always yields the same
token, so entity resolution works on tokens and the graph never holds a real value.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, field
from typing import Any

from core.pii.kms import KMS, default_kms
from core.pii.recognisers import find_spans

TOKEN_RE = re.compile(r"<([A-Z]+)_([0-9a-f]{4,8})>")

# Display names seen in adapter metadata become a per-tenant gazetteer, which is how person
# names are caught without a Swedish NER model (docs/QUESTIONS.md OQ-06-1).
_GAZETTEER: dict[str, set[str]] = {}


def learn_names(tenant_id: str, names: list[str]) -> None:
    bucket = _GAZETTEER.setdefault(tenant_id, set())
    for name in names:
        cleaned = name.strip()
        if len(cleaned) > 3 and " " in cleaned:
            bucket.add(cleaned)


def known_names(tenant_id: str) -> frozenset[str]:
    return frozenset(_GAZETTEER.get(tenant_id, set()))


# Short enough to be an ordinary word as often as a name. "Ek" is a Swedish surname and also
# the word for oak; masking every oak would destroy the meaning of the text it is protecting.
MIN_ALIAS = 3


def name_aliases(tenant_id: str) -> dict[str, str]:
    """Every form a known person's name is written in, mapped to the name it belongs to.

    A gazetteer of full names only catches a full name, and almost nothing is written that way.
    People are greeted by their first name and referred to by their surname, so "Hej Nils" left
    a real name in clear text in every email that opened with it.

    The value an alias maps to is what the token is derived from, so "Nils" and "Nils Ahlgren"
    become the same person rather than two. Where an alias is ambiguous — two colleagues called
    Anna — it maps to itself instead: masked, but deliberately not resolved, because guessing
    which Anna was meant is worse than admitting we cannot tell.
    """
    aliases: dict[str, str] = {}
    ambiguous: set[str] = set()
    for full in _GAZETTEER.get(tenant_id, set()):
        aliases[full] = full
        for part in full.split():
            part = part.strip(".,;:")
            if len(part) < MIN_ALIAS or part == full:
                continue
            if part in aliases and aliases[part] != full:
                ambiguous.add(part)
            else:
                aliases[part] = full
    for part in ambiguous:
        aliases[part] = part
    return aliases


@dataclass
class TokenMap:
    """token -> real value. Redacts itself in every representation."""

    _values: dict[str, str] = field(default_factory=dict)
    _types: dict[str, str] = field(default_factory=dict)

    def add(self, token: str, value: str, entity_type: str) -> None:
        self._values[token] = value
        self._types[token] = entity_type

    def get(self, token: str) -> str | None:
        return self._values.get(token)

    def entity_type(self, token: str) -> str | None:
        return self._types.get(token)

    @property
    def tokens(self) -> list[str]:
        return list(self._values)

    def items_for_vault(self) -> list[tuple[str, str, str]]:
        return [(t, self._types[t], v) for t, v in self._values.items()]

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"TokenMap(<{len(self._values)} redacted values>)"

    __str__ = __repr__


class Boundary:
    def __init__(self, kms: KMS | None = None) -> None:
        self.kms = kms or default_kms()

    def token_for(self, tenant_id: str, entity_type: str, value: str) -> str:
        digest = hmac.new(
            self.kms.data_key(tenant_id),
            f"{entity_type}:{value.strip().lower()}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"<{entity_type}_{digest[:4]}>"

    def tokenize_text(
        self, text: str, *, tenant_id: str, token_map: TokenMap | None = None
    ) -> tuple[str, TokenMap]:
        tmap = token_map if token_map is not None else TokenMap()
        spans = find_spans(text, name_aliases(tenant_id))
        if not spans:
            return text, tmap
        out: list[str] = []
        cursor = 0
        for span in spans:
            token = self.token_for(tenant_id, span.entity_type, span.value)
            out.append(text[cursor : span.start])
            out.append(token)
            tmap.add(token, span.value, span.entity_type)
            cursor = span.end
        out.append(text[cursor:])
        return "".join(out), tmap

    def tokenize(
        self, value: Any, *, tenant_id: str, token_map: TokenMap | None = None
    ) -> tuple[Any, TokenMap]:
        tmap = token_map if token_map is not None else TokenMap()
        if isinstance(value, str):
            return self.tokenize_text(value, tenant_id=tenant_id, token_map=tmap)
        if isinstance(value, dict):
            return {
                k: self.tokenize(v, tenant_id=tenant_id, token_map=tmap)[0]
                for k, v in value.items()
            }, tmap
        if isinstance(value, list):
            return [self.tokenize(v, tenant_id=tenant_id, token_map=tmap)[0] for v in value], tmap
        return value, tmap


_boundary: Boundary | None = None


def get_boundary() -> Boundary:
    global _boundary
    if _boundary is None:
        _boundary = Boundary()
    return _boundary


def tokenize(value: Any, *, tenant_id: str) -> tuple[Any, TokenMap]:
    return get_boundary().tokenize(value, tenant_id=tenant_id)


def restore(value: Any, token_map: TokenMap) -> Any:
    """Turn tokens back into real values. Called only from core/action/executor.py."""
    if isinstance(value, str):

        def sub(match: re.Match[str]) -> str:
            real = token_map.get(match.group(0))
            if real is None:
                raise UnknownTokenError(match.group(0))
            return real

        return TOKEN_RE.sub(sub, value)
    if isinstance(value, dict):
        return {k: restore(v, token_map) for k, v in value.items()}
    if isinstance(value, list):
        return [restore(v, token_map) for v in value]
    return value


class UnknownTokenError(KeyError):
    """A token reached the executor with no vault entry; the write must abort."""


def scan(text: str, tenant_id: str) -> list[tuple[str, str]]:
    """(entity_type, value) pairs a caller would leak. Used by tests and the leak check."""
    return [(s.entity_type, s.value) for s in find_spans(text, known_names(tenant_id))]
