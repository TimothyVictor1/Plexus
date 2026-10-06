-- The shadow workforce: what an agent would have done, recorded before anyone acts.
--
-- An agent shadows a person the way a new colleague does. Every time work comes up it writes
-- down privately what it would do, touches nothing, and waits to see what the person actually
-- does. The comparison is the whole point: it is how an agent earns the right to act, and the
-- only evidence that makes "let it handle this" a decision rather than a leap of faith.
--
-- Predictions are never deleted or rewritten. A record that can be tidied up afterwards proves
-- nothing, which is the same reason the ledger is append-only.

CREATE TABLE IF NOT EXISTS shadow_runs (
  id            uuid PRIMARY KEY,
  tenant_id     text NOT NULL,
  process_id    text NOT NULL,
  agent         text NOT NULL,
  -- What occasioned the prediction, and the item a person eventually saw, if one was shown.
  trigger_kind  text NOT NULL DEFAULT '',
  dedupe_key    text NOT NULL DEFAULT '',
  review_item_id uuid,

  predicted      jsonb NOT NULL,
  predicted_at   timestamptz NOT NULL DEFAULT now(),
  confidence     double precision NOT NULL DEFAULT 0.0,

  -- Filled in when a person settles the matching item. 'pending' until then: an unscored
  -- prediction must never count towards an agent's record in either direction.
  verdict       text NOT NULL DEFAULT 'pending'
                  CHECK (verdict IN ('pending','agreed','edited','rejected','expired')),
  observed      jsonb,
  observed_at   timestamptz,
  -- Why it was scored that way, in a sentence, so a disputed score can be examined.
  note          text NOT NULL DEFAULT ''
);

-- One prediction per real-world occurrence, however often the shadow pass runs.
CREATE UNIQUE INDEX IF NOT EXISTS shadow_runs_once
  ON shadow_runs (tenant_id, process_id, agent, dedupe_key)
  WHERE dedupe_key <> '';

CREATE INDEX IF NOT EXISTS shadow_runs_scoreboard
  ON shadow_runs (tenant_id, process_id, agent, verdict, predicted_at DESC);

CREATE INDEX IF NOT EXISTS shadow_runs_pending
  ON shadow_runs (tenant_id, review_item_id) WHERE verdict = 'pending';

-- A prediction is evidence. Editing one after the fact would make the record worthless.
CREATE OR REPLACE FUNCTION shadow_runs_immutable() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'shadow_runs is append-only: a prediction cannot be deleted';
  END IF;
  IF OLD.predicted IS DISTINCT FROM NEW.predicted
     OR OLD.predicted_at IS DISTINCT FROM NEW.predicted_at
     OR OLD.agent IS DISTINCT FROM NEW.agent THEN
    RAISE EXCEPTION 'shadow_runs: what was predicted, and when, cannot be changed';
  END IF;
  IF OLD.verdict <> 'pending' AND NEW.verdict <> OLD.verdict THEN
    RAISE EXCEPTION 'shadow_runs: a settled prediction cannot be rescored';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS shadow_runs_guard ON shadow_runs;
CREATE TRIGGER shadow_runs_guard
  BEFORE UPDATE OR DELETE ON shadow_runs
  FOR EACH ROW EXECUTE FUNCTION shadow_runs_immutable();

ALTER TABLE shadow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shadow_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON shadow_runs;
CREATE POLICY tenant_isolation ON shadow_runs
  USING (tenant_id = current_setting('plexus.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('plexus.tenant_id', true));
