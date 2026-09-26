-- Plain-language labels (redesign B2).
-- Three sources, in precedence order: a person's correction, a cached generated label, and a
-- rule-based fallback computed on the fly. Only the first two are stored.

CREATE TABLE IF NOT EXISTS label_overrides (
  tenant_id  text NOT NULL,
  kind       text NOT NULL,
  target_id  text NOT NULL,
  text       text NOT NULL,
  author     text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, kind, target_id)
);

CREATE TABLE IF NOT EXISTS label_cache (
  tenant_id  text NOT NULL,
  kind       text NOT NULL,
  target_id  text NOT NULL,
  signature  text NOT NULL,   -- structure hash; a new shape invalidates the old wording
  payload    jsonb NOT NULL,
  source     text NOT NULL,   -- 'model' or 'rules'
  model      text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, kind, target_id)
);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['label_overrides', 'label_cache'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''plexus.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''plexus.tenant_id'', true))', t);
  END LOOP;
END $$;
