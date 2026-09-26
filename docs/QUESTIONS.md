# Questions for the product owner

Open questions the specs could not settle. Each has the conservative interpretation Plexus is
currently built with. Answer inline; decisions move to an ADR.

| Id | Question | Current assumption | Recommendation |
|---|---|---|---|
| OQ-09-1 | Non-Anthropic model ids in the brief (`gpt-5.5`, `qwen3.6-plus`, `deepseek-v4`, `glm-5.3`) could not be verified from this environment. The Anthropic ids are verified current. | Config keeps the brief's ids; router boot-time `list_models()` check in Phase 1 will fail loudly if any is wrong. | Confirm you have OpenAI API access for the verifier, or choose Google as the verifier vendor. |
| OQ-09-2 | The `sovereign` profile puts actor and verifier on the same vendor (`local`), which contradicts "different vendor" literally. | `separation: model` allowed only for local profiles; different model families required. | Approve via ADR-0002 before Phase 1 ships the router. |
| OQ-09-3 | Embedding default: brief says Anthropic-recommended provider with `bge-m3` fallback. | `bge-m3` local as default for the pilot. | Keep local for the TCL pilot (no data leaves the laptop); evaluate hosted in `evals/model_selection.md`. |
| OQ-04-1 | `recency_factor` shape is unspecified. | `1 - exp(-days/14)`. | Confirm before Phase 3. |
| OQ-04-2 | Hash chain per (tenant, process) or per tenant? | Per process, plus nightly tenant-wide Merkle root entry. | Confirm. |
| OQ-05-1 | Should `AUTONOMOUS` ever be allowed for `risk_class = high`? | No; capped at `ACT_WITH_APPROVAL` (`config/trust.yaml`). | Confirm. |
| OQ-01-3 | MCP transport in compose: stdio or streamable HTTP? | Streamable HTTP, one container per adapter. | Confirm. |
| OQ-02-2 | May `pm4py` be a dev-only dependency to validate the pure-Python miner? | Not added yet. | Yes, dev-only. (Open source, no paid dependency.) |
| OQ-11-1 | IdP at TCL: Keycloak brokering Google Workspace, or Google directly? | Keycloak. | Keycloak brokering Google keeps RBAC in Plexus. |
| OQ-00-1 | Tenant id as slug or UUID? | Slug, with a `tenants` table. | Slug for the pilot. |
| OQ-06-3 | The token vault encrypts with a Blake2b keystream rather than AES-256-GCM, to avoid a crypto dependency in the pilot. | Blake2b keystream; the KMS interface and per-tenant data key are the real ones. | Swap to AES-256-GCM via `cryptography` before any customer data. It is a change inside `core/pii/vault.py`. Needs your approval for the dependency. |
| OQ-09-4 | Every model role currently resolves to the deterministic local provider, so the pipeline runs with no API key. | Local provider for all roles; the vendor-separation check still runs against the configured vendors. | Confirm which hosted vendors to wire first, then the router's provider map is the only change. |

## Honest concerns about the brief (working method §10.10)

1. **Phase 0 DoD "compose stack boots on a clean machine"** pulls roughly 6–8 GB of images
   (Neo4j, Keycloak, Temporal, two Presidio images with spaCy models). It works, but first boot
   on a laptop is 10–20 minutes. Recommendation: keep it, and add a `make up-core` target in
   Phase 1 that boots only Postgres/Neo4j/Redis/Temporal for day-to-day development.
2. **Presidio's official images do not include Swedish spaCy models.** Spec 06 assumes custom
   recognisers plus `sv_core_news_lg`; that means a custom analyzer image built from
   `mcr.microsoft.com/presidio-analyzer` with the Swedish model added. Phase 1 will build it
   under `docker/presidio-analyzer-sv/`. No paid dependency, but a bigger image.
3. **Two-vendor rule vs. sovereign profile** (OQ-09-2) is a genuine contradiction in the brief;
   see the recommendation above.
4. **Verifier vendor `openai` is a paid external dependency** already listed in the brief, so no
   further approval is sought for it; adding Google as a fallback verifier would be a new one
   and will be asked for explicitly.
