-- Things waiting for a person (redesign B5).
-- A review item wraps an existing proposed_action rather than duplicating it, so approving
-- still runs through the one write path.

CREATE TABLE IF NOT EXISTS review_items (
  id             uuid PRIMARY KEY,
  tenant_id      text NOT NULL,
  process_id     text NOT NULL,
  action_id      uuid REFERENCES proposed_actions (id) ON DELETE SET NULL,
  kind           text NOT NULL,
  title          text NOT NULL,
  why            text NOT NULL,
  draft_text     text NOT NULL DEFAULT '',
  draft_fields   jsonb NOT NULL DEFAULT '{}'::jsonb,
  approve_label  text NOT NULL DEFAULT 'Approve',
  status         text NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open','approved','edited','skipped','executed','failed')),
  result         jsonb,
  error          text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  decided_by     text,
  decided_at     timestamptz
);
CREATE INDEX IF NOT EXISTS review_items_open ON review_items (tenant_id, status, created_at DESC);

-- One item per real-world occurrence, however often the trigger check runs.
CREATE TABLE IF NOT EXISTS triggers_seen (
  tenant_id  text NOT NULL,
  process_id text NOT NULL,
  dedupe_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, process_id, dedupe_key)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['review_items', 'triggers_seen'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''plexus.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''plexus.tenant_id'', true))', t);
  END LOOP;
END $$;
