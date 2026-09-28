-- Inviting colleagues, and a record of the work that runs in the background.

CREATE TABLE IF NOT EXISTS invites (
  id         uuid PRIMARY KEY,
  tenant_id  text NOT NULL,
  email      text NOT NULL,
  role       text NOT NULL CHECK (role IN ('viewer','operator','approver','admin')),
  token      text NOT NULL UNIQUE,
  status     text NOT NULL DEFAULT 'pending'
               CHECK (status IN ('pending','accepted','revoked','expired')),
  invited_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz,
  UNIQUE (tenant_id, email, status)
);

-- What ran, when, and whether it worked. The background is where most of the system's work
-- happens, so it needs to be as visible as anything a person clicks.
CREATE TABLE IF NOT EXISTS job_runs (
  id          uuid PRIMARY KEY,
  tenant_id   text NOT NULL,
  job         text NOT NULL,
  status      text NOT NULL CHECK (status IN ('running','ok','failed')),
  detail      text NOT NULL DEFAULT '',
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS job_runs_recent ON job_runs (tenant_id, job, started_at DESC);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['invites', 'job_runs'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''plexus.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''plexus.tenant_id'', true))', t);
  END LOOP;
END $$;
