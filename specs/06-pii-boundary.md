# Spec 06 — PII Boundary (Pillar 6)

Status: draft (Phase 0) · Phase: 1 · Source: brief §5 Pillar 6, §2 principle 2

## Purpose

Models never see clear-text personal data; customer systems never receive tokens. GDPR erasure
is a single operation on the vault.

## Inputs

- Text or structured dicts leaving an adapter (every `SourceItem`, every `SourceEvent`).
- Tokenised payloads entering the executor for write-back.
- Erasure requests by subject token.

## Outputs

- Tokenised text/dicts and a `TokenMap` (in-process, never persisted outside the vault).
- Vault rows (encrypted at rest, per-tenant key).
- Recognition metrics per recogniser (for evals).

## Data model changes

### Tokens

Format-preserving, per-tenant stable: `<PERSON_7f3a>`, `<ORG_9c21>`, `<PNR_1b0e>`,
`<PHONE_44d2>`, `<IBAN_a9f0>`, `<ADDRESS_e7c3>`, `<EMAIL_2d8b>`. The suffix is the first 4 hex
chars of `HMAC(tenant_key, normalised_value)` with collision extension to 8 chars. Stability
means the same person yields the same token across sources, so entity resolution works on
tokens without the graph ever holding the real value.

### Recognisers (`core/pii/recognisers/`)

Presidio analyzer plus custom recognisers: Swedish personnummer/samordningsnummer (with Luhn
check and date validation), Swedish org-nr, phone (`+46`, `0xx-` formats), IBAN/Bankgiro/
Plusgiro, Swedish street addresses, person names (spaCy `sv_core_news_lg` + `en_core_web_lg`),
email addresses.

### Vault (`core/pii/vault.py`)

`token_vault(tenant_id, token, entity_type, ciphertext bytea, nonce, key_version, created_at,
erased_at)` with RLS. Encryption: AES-256-GCM with a per-tenant data key wrapped by the KMS
abstraction (`core/pii/kms.py`: `FileKMS` for dev, interface for cloud KMS later).

### Erasure

`DELETE /v1/tenants/{t}/subjects/{token}` (role `admin`): vault row marked `erased_at` and
ciphertext zeroed; graph nodes referencing the token set `erased = true`; documents and chunks
whose `structured`/`actors` reference the token are purged; embeddings need no recompute (they
were computed over tokenised text). A ledger-like `erasure_log` records the request.

## Interfaces

```python
# core/pii/boundary.py
def tokenize(value: str | dict[str, Any], *, tenant_id: str) -> tuple[str | dict[str, Any], TokenMap]
def restore(value: str | dict[str, Any], token_map: TokenMap) -> str | dict[str, Any]
class TokenMap(Mapping[str, str]): ...   # token -> real value; repr/str redact values
```

`tokenize` is applied by the adapter base class in `_emit()`. `restore` is imported only by
`core/action/executor.py` (architecture test). Log formatters (`core/logging.py`) refuse to
serialise a `TokenMap` and scrub anything matching a recogniser as a last line of defence.

## Failure modes

| Failure | Behaviour |
|---|---|
| Presidio unavailable | Adapter emission blocks (fail closed); health shows `pii: down`. Nothing untokenised is ever emitted. |
| Recogniser false positive | Value is tokenised anyway; over-tokenisation is acceptable, under-tokenisation is not. |
| Token collision | Suffix extended to 8 hex chars; vault unique constraint on `(tenant_id, token)`. |
| Restore with unknown token | Executor aborts the write; `execution` recorded with `ok=false, reason=unknown_token`. |
| Vault key unavailable | Reads and writes fail closed. |

## Acceptance tests

- AT-06-1: Hypothesis fuzz over 10 000 generated Swedish/English strings with embedded PII of
  every recogniser type: recall ≥ 99% per type; `restore(tokenize(x)) == x` for all x.
- AT-06-2: After a full demo run, a grep of all model request logs finds zero matches for the
  seeded real values in `scripts/fixtures/labels/pii.json`.
- AT-06-3: `TokenMap.__repr__` and JSON serialisation never contain real values.
- AT-06-4: Only `core/action/executor.py` imports `restore` (architecture test).
- AT-06-5: Erasure removes the vault entry, marks nodes `erased`, and purges documents within
  one API call; a subsequent Explain query does not return the subject.

## Open questions

- OQ-06-1: spaCy Swedish NER quality on names is mediocre. Recommendation: combine with a
  gazetteer built from tokenised adapter actor fields (email display names) and measure in evals.
- OQ-06-2: Whether to run Presidio in-process (library) instead of the two compose containers.
  Recommendation: containers for parity with deployment; in-process only for unit tests.
