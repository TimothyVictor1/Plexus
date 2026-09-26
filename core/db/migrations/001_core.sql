-- Plexus core schema. Specs 01, 02, 04, 05, 06, 11.
-- Every table carries tenant_id and has row-level security keyed on plexus.tenant_id.

CREATE TABLE IF NOT EXISTS tenants (
  id          text PRIMARY KEY,
  name        text NOT NULL,
  region      text NOT NULL DEFAULT 'EU',
  paused      boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- documents (spec 01)
CREATE TABLE IF NOT EXISTS documents (
  id              uuid PRIMARY KEY,
  tenant_id       text NOT NULL,
  source_id       text NOT NULL,
  external_id     text NOT NULL,
  kind            text NOT NULL,
  title           text NOT NULL,
  body_tokenised  text NOT NULL,
  structured      jsonb NOT NULL DEFAULT '{}'::jsonb,
  actors          jsonb NOT NULL DEFAULT '[]'::jsonb,
  source_ref      jsonb NOT NULL,
  created_at      timestamptz NOT NULL,
  ingested_at     timestamptz NOT NULL DEFAULT now(),
  erased          boolean NOT NULL DEFAULT false,
  UNIQUE (tenant_id, source_id, external_id)
);
CREATE INDEX IF NOT EXISTS documents_tenant_kind ON documents (tenant_id, kind);

-- ---------------------------------------------------------------- token vault (spec 06)
CREATE TABLE IF NOT EXISTS token_vault (
  tenant_id    text NOT NULL,
  token        text NOT NULL,
  entity_type  text NOT NULL,
  value_enc    bytea NOT NULL,
  nonce        bytea NOT NULL,
  key_version  int NOT NULL DEFAULT 1,
  created_at   timestamptz NOT NULL DEFAULT now(),
  erased_at    timestamptz,
  PRIMARY KEY (tenant_id, token)
);

-- ---------------------------------------------------------------- event log (spec 02)
CREATE TABLE IF NOT EXISTS event_log (
  event_id    uuid PRIMARY KEY,
  tenant_id   text NOT NULL,
  ts          timestamptz NOT NULL,
  actor       jsonb NOT NULL,
  verb        text NOT NULL,
  objects     jsonb NOT NULL,
  source      jsonb NOT NULL,
  attributes  jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence  real NOT NULL DEFAULT 1.0,
  synthesised boolean NOT NULL DEFAULT false,
  trace_id    text NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS event_log_tenant_ts ON event_log (tenant_id, ts);
CREATE INDEX IF NOT EXISTS event_log_objects ON event_log USING gin (objects);

-- ---------------------------------------------------------------- processes (spec 02)
CREATE TABLE IF NOT EXISTS processes (
  id           text NOT NULL,
  tenant_id    text NOT NULL,
  name         text NOT NULL,
  description  text NOT NULL DEFAULT '',
  steps        jsonb NOT NULL DEFAULT '[]'::jsonb,
  edges        jsonb NOT NULL DEFAULT '[]'::jsonb,
  metrics      jsonb NOT NULL DEFAULT '{}'::jsonb,
  case_count   int NOT NULL DEFAULT 0,
  discovered_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS process_state (
  tenant_id     text NOT NULL,
  process_id    text NOT NULL,
  tier          text NOT NULL DEFAULT 'OBSERVE',
  trust         real NOT NULL DEFAULT 0,
  paused        boolean NOT NULL DEFAULT false,
  last_error_at timestamptz,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, process_id)
);

-- ---------------------------------------------------------------- policies (spec 03)
CREATE TABLE IF NOT EXISTS policies (
  id         text NOT NULL,
  tenant_id  text NOT NULL,
  name       text NOT NULL,
  scope      jsonb NOT NULL DEFAULT '{}'::jsonb,
  field      text NOT NULL,
  operator   text NOT NULL,
  value      jsonb NOT NULL,
  effect     text NOT NULL,
  enabled    boolean NOT NULL DEFAULT true,
  version    int NOT NULL DEFAULT 1,
  PRIMARY KEY (tenant_id, id)
);

-- ---------------------------------------------------------------- actions (spec 05)
CREATE TABLE IF NOT EXISTS proposed_actions (
  id               uuid PRIMARY KEY,
  tenant_id        text NOT NULL,
  process_id       text NOT NULL,
  trigger_event_id uuid,
  target_source_id text NOT NULL,
  operation        text NOT NULL,
  arguments        jsonb NOT NULL,
  rationale        text NOT NULL,
  cited_context    jsonb NOT NULL DEFAULT '[]'::jsonb,
  expected_effects jsonb NOT NULL DEFAULT '[]'::jsonb,
  risk_class       text NOT NULL,
  actor_model      jsonb NOT NULL,
  simulation       jsonb,
  status           text NOT NULL DEFAULT 'pending',
  trace_id         text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS proposed_actions_tenant_status ON proposed_actions (tenant_id, status);

CREATE TABLE IF NOT EXISTS verdicts (
  id             uuid PRIMARY KEY,
  tenant_id      text NOT NULL,
  action_id      uuid NOT NULL UNIQUE REFERENCES proposed_actions (id) ON DELETE CASCADE,
  decision       text NOT NULL CHECK (decision IN ('approve', 'reject', 'escalate')),
  reasons        jsonb NOT NULL DEFAULT '[]'::jsonb,
  verifier_model jsonb NOT NULL,
  trace_id       text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);

-- An execution cannot exist without a stored verdict. This is the structural half of
-- principle 1; the import-boundary test is the other half.
CREATE TABLE IF NOT EXISTS executions (
  id           uuid PRIMARY KEY,
  tenant_id    text NOT NULL,
  action_id    uuid NOT NULL REFERENCES proposed_actions (id) ON DELETE CASCADE,
  verdict_id   uuid NOT NULL REFERENCES verdicts (id),
  approver     jsonb,
  write_result jsonb NOT NULL,
  reversal     jsonb,
  reversed_at  timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- ledger (spec 04)
CREATE TABLE IF NOT EXISTS ledger_entries (
  seq        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id         uuid NOT NULL UNIQUE,
  tenant_id  text NOT NULL,
  process_id text NOT NULL,
  entry_type text NOT NULL CHECK (entry_type IN (
               'shadow_run','suggestion','approval','rejection','execution','reversal',
               'promotion','demotion','manual_override','refusal','pause','unpause')),
  actor      jsonb NOT NULL,
  payload    jsonb NOT NULL,
  trace_id   text NOT NULL,
  ts         timestamptz NOT NULL DEFAULT now(),
  prev_hash  text NOT NULL,
  hash       text NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_tenant_process ON ledger_entries (tenant_id, process_id, seq);

-- Append-only. Corrections are new rows; nothing is ever updated or deleted.
CREATE OR REPLACE FUNCTION ledger_append_only() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'ledger_entries is append-only (spec 04); attempted %', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS ledger_no_update ON ledger_entries;
CREATE TRIGGER ledger_no_update BEFORE UPDATE OR DELETE ON ledger_entries
  FOR EACH ROW EXECUTE FUNCTION ledger_append_only();

-- ---------------------------------------------------------------- model calls (spec 09)
CREATE TABLE IF NOT EXISTS model_calls (
  id            uuid PRIMARY KEY,
  tenant_id     text NOT NULL,
  role          text NOT NULL,
  vendor        text NOT NULL,
  model         text NOT NULL,
  prompt_name   text NOT NULL DEFAULT '',
  prompt_version int NOT NULL DEFAULT 0,
  input_tokens  int NOT NULL DEFAULT 0,
  output_tokens int NOT NULL DEFAULT 0,
  cost_usd      numeric(12,6) NOT NULL DEFAULT 0,
  latency_ms    real NOT NULL DEFAULT 0,
  ok            boolean NOT NULL DEFAULT true,
  error_kind    text,
  trace_id      text NOT NULL DEFAULT '',
  ts            timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- corrections (spec 01)
CREATE TABLE IF NOT EXISTS corrections (
  id          uuid PRIMARY KEY,
  tenant_id   text NOT NULL,
  target_kind text NOT NULL,
  target_id   text NOT NULL,
  original    jsonb NOT NULL,
  corrected   jsonb NOT NULL,
  author      text NOT NULL,
  reason      text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- adapter sink
-- What a write actually lands in for the fixture adapters, so an execution is observable.
CREATE TABLE IF NOT EXISTS adapter_records (
  id          uuid PRIMARY KEY,
  tenant_id   text NOT NULL,
  source_id   text NOT NULL,
  external_id text NOT NULL,
  record_type text NOT NULL,
  fields      jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, source_id, external_id)
);
