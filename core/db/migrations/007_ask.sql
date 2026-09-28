-- Asking questions about your own company (redesign B6).

-- Full-text search over what has been ingested. The text is already tokenised, so the index
-- holds placeholders rather than anyone's name.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS search_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(body_tokenised, ''))
  ) STORED;
CREATE INDEX IF NOT EXISTS documents_search ON documents USING gin (search_tsv);

CREATE TABLE IF NOT EXISTS conversations (
  id         uuid PRIMARY KEY,
  tenant_id  text NOT NULL,
  subject    text NOT NULL,
  title      text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  id              uuid PRIMARY KEY,
  tenant_id       text NOT NULL,
  conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
  role            text NOT NULL CHECK (role IN ('user', 'assistant')),
  text            text NOT NULL,
  sources         jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_conversation ON messages (tenant_id, conversation_id, created_at);

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['conversations', 'messages'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''plexus.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''plexus.tenant_id'', true))', t);
  END LOOP;
END $$;
