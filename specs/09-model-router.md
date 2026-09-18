# Spec 09 — Model router

Status: draft (Phase 0) · Phase: 1 · Source: brief §6, §2 principles 3 and 9

## Purpose

One place for every model call: role-based routing, vendor separation enforcement, structured
output validation, retries, cost accounting, timeouts, circuit breaking, prompt caching, and
tracing. No file outside `core/models/` imports a vendor SDK.

## Inputs

- `config/models.yaml` (roles, profiles) and `PLEXUS_MODEL_PROFILE`.
- Prompt files `prompts/*.md` with a version header.
- Calls: `complete(role, messages, tools=None, schema=None, *, tenant_id, trace_ctx)`.

## Outputs

- `Completion` (text or schema-validated Pydantic instance, tool calls, usage, cost, model id,
  prompt version).
- `model_calls` rows for per-tenant cost accounting.
- OpenTelemetry spans per call.

## Data model changes

```yaml
# config/models.yaml
roles:
  actor:      { vendor: anthropic, model: claude-fable-5-1, effort: high }
  workhorse:  { vendor: anthropic, model: claude-sonnet-5 }
  classifier: { vendor: anthropic, model: claude-haiku-4-5 }
  verifier:   { vendor: openai,    model: gpt-5.5 }        # MUST differ from actor vendor
  embedder:   { vendor: local,     model: bge-m3 }
profiles:
  sovereign:
    actor:     { vendor: local, model: qwen3.6-plus }
    verifier:  { vendor: local, model: deepseek-v4 }
    workhorse: { vendor: local, model: glm-5.3 }
```

Note on `sovereign`: all roles resolve to vendor `local`, so vendor separation must be checked
at the model level for local profiles (`actor.model != verifier.model`) and the config must
declare that explicitly (`separation: model`). See OQ-09-2.

Postgres: `model_calls(id, tenant_id, role, vendor, model, prompt_name, prompt_version,
input_tokens, output_tokens, cache_read_tokens, cost_usd, latency_ms, ok, error_kind, trace_id, ts)`.
Price table in `config/model_prices.yaml`.

Prompt files: `prompts/{name}.md` starting with a YAML header
`--- name, version, role, schema (optional), description ---`; loader refuses files without it.

## Interfaces

```python
# core/models/router.py
class Router:
    @classmethod
    def from_config(cls, path: Path, env: Env, profile: str) -> Router   # raises VendorSeparationError
    async def complete(self, role: Role, messages: list[Message], *, tools: list[Tool] | None = None,
                       schema: type[BaseModel] | None = None, tenant_id: str,
                       prompt: PromptRef | None = None) -> Completion
    async def embed(self, texts: list[str], *, tenant_id: str) -> list[list[float]]

# core/models/providers/{anthropic,openai,google,local}.py implement Provider protocol
class Provider(Protocol):
    vendor: str
    async def complete(self, req: ProviderRequest) -> ProviderResponse
    async def embed(self, req: EmbedRequest) -> EmbedResponse
    async def list_models(self) -> list[str]
```

Behaviour:
- Structured output enforced by JSON schema at the vendor (where supported) and validated by
  Pydantic; one automatic retry with the validation error appended.
- Per-vendor timeout and circuit breaker (open after `n` failures in `window`, half-open probe).
- Prompt caching enabled for stable prefixes (system prompt + tool list) on vendors that support it.
- Anthropic provider: adaptive thinking on (Fable and Opus families reject `budget_tokens`);
  `output_config.effort` from role config; handle `stop_reason == "refusal"`; streaming for long
  outputs. Model ids are used exactly as listed by the vendor's Models API.
- `list_models()` is called at boot in non-test envs; a configured model id missing from the
  vendor list fails boot with a clear message (brief §6: verify model names at build time).
- In `env=production`, `from_config` raises if `roles.actor.vendor == roles.verifier.vendor`
  (or, for `separation: model`, if the models are equal).

## Failure modes

| Failure | Behaviour |
|---|---|
| Invalid JSON twice | `SchemaValidationError` with both raw responses attached; caller decides. |
| Vendor timeout / 5xx | Retried per SDK defaults; circuit opens after threshold; `ModelUnavailable` raised. |
| Circuit open | Fail fast; span tagged `circuit_open`. |
| Refusal stop reason (Anthropic) | `ModelRefused` with category; never retried on a different vendor for verifier calls. |
| Cost row insert fails | Call still returns; cost written to a Redis backlog and replayed. |
| Vendor separation violated in production | Boot fails. |

## Acceptance tests

- AT-09-1: `from_config` raises `VendorSeparationError` in `env=production` when actor and
  verifier share a vendor; does not raise in `development` (warns).
- AT-09-2: A fake provider returning invalid JSON once then valid JSON → one retry, success;
  twice invalid → `SchemaValidationError`.
- AT-09-3: Every call writes a `model_calls` row with `tenant_id` and `trace_id`.
- AT-09-4: Circuit breaker opens after configured failures and half-opens after the window.
- AT-09-5: Architecture test: no module outside `core/models/providers/` imports `anthropic`,
  `openai`, `google.genai`, `google.generativeai`, or `ollama`.
- AT-09-6: Prompt loader rejects a prompt file without a version header.

## Open questions

- OQ-09-1: Non-Anthropic model ids in the brief (`gpt-5.5`, `qwen3.6-plus`, `deepseek-v4`,
  `glm-5.3`) are unverified as of Phase 0. The Anthropic ids are verified current. Verify the
  others at Phase 1 boot via `list_models()` and update the config.
- OQ-09-2: The `sovereign` profile puts actor and verifier on the same vendor (`local`). The
  brief's "different vendor" rule cannot hold literally there. Recommendation: allow
  `separation: model` for local profiles with an explicit ADR, and require different model
  families (not just different quantisations).
- OQ-09-3: Embedding default: brief says "Anthropic-recommended provider, fallback bge-m3".
  Recommendation: `bge-m3` local as default for the pilot (no data leaves the laptop),
  evaluate a hosted multilingual embedder in `evals/model_selection.md`.
