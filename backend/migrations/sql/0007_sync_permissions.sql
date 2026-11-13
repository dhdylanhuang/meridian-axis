-- Fixed-account sync writer. Password maintenance is a separate private operation.
DO $sync_permissions$
DECLARE target_schema text := current_schema(); writer text; reader text; tab text;
BEGIN
  IF NOT (target_schema='public' OR target_schema ~ '^meridian_test_[0-9a-f]{32}$')
  THEN RAISE EXCEPTION 'Sync requires reviewed schema'; END IF;
  writer := 'meridian_sync_' || target_schema;
  reader := 'meridian_bff_' || target_schema;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=writer)
  THEN RAISE EXCEPTION 'Sync role already exists'; END IF;
  EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS', writer);
  EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', target_schema, writer);
  FOREACH tab IN ARRAY ARRAY['broker_sync_jobs','broker_rate_limits','broker_event_revisions'] LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, tab);
    EXECUTE format('REVOKE ALL ON %I.%I FROM PUBLIC', target_schema, tab);
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
      EXECUTE format('REVOKE ALL ON %I.%I FROM anon', target_schema, tab);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
      EXECUTE format('REVOKE ALL ON %I.%I FROM authenticated', target_schema, tab);
    END IF;
  END LOOP;
  FOREACH tab IN ARRAY ARRAY['import_log','source_records','broker_snapshots','broker_sync_jobs','broker_rate_limits','broker_event_revisions'] LOOP
    EXECUTE format('GRANT SELECT ON %I.%I TO %I', target_schema, tab, writer);
    EXECUTE format('CREATE POLICY meridian_sync_read ON %I.%I FOR SELECT TO %I USING (account_id = %L)', target_schema, tab, writer, 'shared-isa');
  END LOOP;
  EXECUTE format('GRANT SELECT ON %I.accounts TO %I', target_schema, writer);
  EXECUTE format('CREATE POLICY meridian_sync_account_read ON %I.accounts FOR SELECT TO %I USING (id = %L)', target_schema, writer, 'shared-isa');
  FOREACH tab IN ARRAY ARRAY['import_log','source_records','broker_snapshots','broker_sync_jobs','broker_rate_limits','broker_event_revisions'] LOOP
    EXECUTE format('GRANT INSERT ON %I.%I TO %I', target_schema, tab, writer);
    EXECUTE format('CREATE POLICY meridian_sync_insert ON %I.%I FOR INSERT TO %I WITH CHECK (account_id = %L)', target_schema, tab, writer, 'shared-isa');
  END LOOP;
  FOREACH tab IN ARRAY ARRAY['broker_sync_jobs','broker_rate_limits'] LOOP
    EXECUTE format('GRANT UPDATE ON %I.%I TO %I', target_schema, tab, writer);
    EXECUTE format('CREATE POLICY meridian_sync_update ON %I.%I FOR UPDATE TO %I USING (account_id = %L) WITH CHECK (account_id = %L)', target_schema, tab, writer, 'shared-isa', 'shared-isa');
  END LOOP;
  EXECUTE format('GRANT UPDATE (status, content_hash, finished_at, error_code, counts_json) ON %I.import_log TO %I', target_schema, writer);
  EXECUTE format('CREATE POLICY meridian_sync_import_update ON %I.import_log FOR UPDATE TO %I USING (account_id = %L AND kind IN (%L,%L,%L,%L,%L)) WITH CHECK (account_id = %L)', target_schema, writer, 'shared-isa', 'trading212_refresh','trading212_history_orders','trading212_history_dividends','trading212_history_transactions','trading212_metadata', 'shared-isa');
  EXECUTE format('GRANT INSERT ON %I.audit_log TO %I', target_schema, writer);
  EXECUTE format('CREATE POLICY meridian_sync_audit ON %I.audit_log FOR INSERT TO %I WITH CHECK (actor = %L AND run_id IN (SELECT id FROM %I.import_log WHERE account_id = %L))', target_schema, writer, 'broker-sync', target_schema, 'shared-isa');
  EXECUTE format('GRANT SELECT (account_id,task,next_attempt_at,last_attempt_at,last_success_at,failures,error_code) ON %I.broker_sync_jobs TO %I', target_schema, reader);
  EXECUTE format('CREATE POLICY meridian_refresh_health ON %I.broker_sync_jobs FOR SELECT TO %I USING (account_id = %L)', target_schema, reader, 'shared-isa');
END $sync_permissions$;
