-- Person-name gazetteer per tenant (spec 06, OQ-06-1).
-- Built from adapter metadata at ingest time so the boundary catches names without a Swedish
-- NER model. It holds names, which are themselves personal data, so it carries RLS like the rest.
CREATE TABLE IF NOT EXISTS pii_gazetteer (
  tenant_id  text NOT NULL,
  name       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, name)
);
ALTER TABLE pii_gazetteer ENABLE ROW LEVEL SECURITY;
ALTER TABLE pii_gazetteer FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON pii_gazetteer;
CREATE POLICY tenant_isolation ON pii_gazetteer
  USING (tenant_id = current_setting('plexus.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('plexus.tenant_id', true));
