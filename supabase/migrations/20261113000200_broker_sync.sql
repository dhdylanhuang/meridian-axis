-- Additive sync migration. The native runner owns the transaction.
DO $revision_check$
BEGIN
 IF (SELECT count(*) FROM alembic_version) <> 1 OR NOT EXISTS
 (SELECT 1 FROM alembic_version WHERE version_num = '0006')
 THEN RAISE EXCEPTION 'Expected schema 0006'; END IF;
END $revision_check$;

CREATE UNIQUE INDEX uq_source_id_account ON source_records (id, account_id);

CREATE TABLE broker_sync_jobs (
	account_id VARCHAR(64) NOT NULL,
	task VARCHAR(32) NOT NULL,
	lease_token VARCHAR(64),
	lease_until TEXT,
	next_attempt_at TEXT NOT NULL,
	last_attempt_at TEXT,
	last_success_at TEXT,
	failures INTEGER NOT NULL,
	error_code VARCHAR(64),
	checkpoint_json TEXT NOT NULL,
	PRIMARY KEY (account_id, task),
	CONSTRAINT ck_sync_failures CHECK (failures >= 0),
	CONSTRAINT ck_sync_task CHECK (task IN ('snapshot','orders','dividends','transactions','metadata')),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE TABLE broker_rate_limits (
	account_id VARCHAR(64) NOT NULL,
	route VARCHAR(128) NOT NULL,
	next_request_at TEXT NOT NULL,
	PRIMARY KEY (account_id, route),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE TABLE broker_event_revisions (
	id VARCHAR(64) NOT NULL,
	account_id VARCHAR(64) NOT NULL,
	family VARCHAR(32) NOT NULL,
	external_id VARCHAR(256) NOT NULL,
	revision INTEGER NOT NULL,
	source_id VARCHAR(64) NOT NULL,
	observed_at TEXT NOT NULL,
	digest VARCHAR(64) NOT NULL,
	payload_json TEXT NOT NULL,
	quality VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_revision_source_account FOREIGN KEY(source_id, account_id) REFERENCES source_records (id, account_id),
	CONSTRAINT uq_event_revision UNIQUE (account_id, family, external_id, revision),
	CONSTRAINT ck_event_revision_positive CHECK (revision > 0),
	CONSTRAINT ck_event_family CHECK (family IN ('orders','dividends','transactions')),
	CONSTRAINT ck_event_digest CHECK (length(digest) = 64),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
);

-- Fixed-account sync writer. Password maintenance is a separate private operation.
DO $sync_permissions$
DECLARE target_schema text := current_schema(); writer text; reader text; tab text; scope_condition text;
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
    scope_condition := 'account_id = ''shared-isa''';
    IF tab = 'source_records' THEN
      scope_condition := scope_condition || ' AND kind IN (''trading212_refresh'',''trading212_history_page'',''trading212_metadata'')';
    ELSIF tab = 'import_log' THEN
      scope_condition := scope_condition || ' AND kind IN (''trading212_refresh'',''trading212_history_orders'',''trading212_history_dividends'',''trading212_history_transactions'',''trading212_metadata'')';
    END IF;
    EXECUTE format('CREATE POLICY meridian_sync_read ON %I.%I FOR SELECT TO %I USING (%s)', target_schema, tab, writer, scope_condition);
  END LOOP;
  EXECUTE format('GRANT SELECT ON %I.accounts TO %I', target_schema, writer);
  EXECUTE format('CREATE POLICY meridian_sync_account_read ON %I.accounts FOR SELECT TO %I USING (id = %L)', target_schema, writer, 'shared-isa');
  FOREACH tab IN ARRAY ARRAY['import_log','source_records','broker_snapshots','broker_sync_jobs','broker_rate_limits','broker_event_revisions'] LOOP
    EXECUTE format('GRANT INSERT ON %I.%I TO %I', target_schema, tab, writer);
    scope_condition := 'account_id = ''shared-isa''';
    IF tab = 'source_records' THEN
      scope_condition := scope_condition || ' AND kind IN (''trading212_refresh'',''trading212_history_page'',''trading212_metadata'')';
    ELSIF tab = 'import_log' THEN
      scope_condition := scope_condition || ' AND kind IN (''trading212_refresh'',''trading212_history_orders'',''trading212_history_dividends'',''trading212_history_transactions'',''trading212_metadata'')';
    END IF;
    EXECUTE format('CREATE POLICY meridian_sync_insert ON %I.%I FOR INSERT TO %I WITH CHECK (%s)', target_schema, tab, writer, scope_condition);
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

UPDATE alembic_version SET version_num = '0007' WHERE version_num = '0006';
