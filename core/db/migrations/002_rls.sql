-- Row-level security on every tenant-scoped table (spec 11).
-- The application connects as the owner in dev, so FORCE is required for policies to apply.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'documents','token_vault','event_log','processes','process_state','policies',
    'proposed_actions','verdicts','executions','ledger_entries','model_calls',
    'corrections','adapter_records'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''plexus.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''plexus.tenant_id'', true))', t);
  END LOOP;
END $$;
