-- Org record and connected tools (redesign B1, B8).
-- The org is the only place a company name lives; nothing in code hardcodes one.

ALTER TABLE tenants ADD COLUMN IF NOT EXISTS display_name text;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS locale text NOT NULL DEFAULT 'en';
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS is_demo boolean NOT NULL DEFAULT false;
UPDATE tenants SET display_name = coalesce(display_name, name);

-- One row per tool a company has connected. Categories are industry-neutral.
CREATE TABLE IF NOT EXISTS connections (
  id          uuid PRIMARY KEY,
  tenant_id   text NOT NULL,
  category    text NOT NULL CHECK (category IN (
                'email','calendar','crm','accounting','files','hr','chat','projects')),
  provider    text NOT NULL,
  status      text NOT NULL DEFAULT 'not_connected'
                CHECK (status IN ('connected','error','not_connected','not_configured')),
  source_id   text,
  last_sync   timestamptz,
  scopes      jsonb NOT NULL DEFAULT '[]'::jsonb,
  config      jsonb NOT NULL DEFAULT '{}'::jsonb,
  detail      text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, category, provider)
);

ALTER TABLE connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE connections FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON connections;
CREATE POLICY tenant_isolation ON connections
  USING (tenant_id = current_setting('plexus.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('plexus.tenant_id', true));

-- Disconnect detaches rather than deletes, so mined processes and ledger provenance survive.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS connection_id uuid;
ALTER TABLE event_log ADD COLUMN IF NOT EXISTS connection_id uuid;
CREATE INDEX IF NOT EXISTS documents_connection ON documents (tenant_id, connection_id);
CREATE INDEX IF NOT EXISTS event_log_connection ON event_log (tenant_id, connection_id);
