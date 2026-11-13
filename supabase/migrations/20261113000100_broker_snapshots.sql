-- Native migration is the sole hosted schema writer. No data seeds.
DO $snapshot_parity$ BEGIN
 IF (SELECT version_num FROM alembic_version) <> '0005'
 THEN RAISE EXCEPTION 'Snapshot migration requires parity 0005'; END IF;
END $snapshot_parity$;

CREATE TABLE broker_snapshots (
	id VARCHAR(64) NOT NULL,
	account_id VARCHAR(64) NOT NULL,
	source_run_id VARCHAR(64) NOT NULL,
	observed_at TEXT NOT NULL,
	created_at TEXT NOT NULL,
	snapshot_json TEXT NOT NULL,
	digest VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_snapshot_source_run_account FOREIGN KEY(source_run_id, account_id) REFERENCES import_log (id, account_id),
	CONSTRAINT uq_snapshot_source_account UNIQUE (source_run_id, account_id),
	CONSTRAINT ck_snapshot_digest_length CHECK (length(digest) = 64),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
)

;
CREATE INDEX ix_snapshot_account_observed ON broker_snapshots (account_id, observed_at);
-- Immutable shared DCL. No credentials, identities or financial seeds.
ALTER TABLE broker_snapshots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE broker_snapshots FROM PUBLIC;
DO $snapshot_access$
DECLARE target_schema text := current_schema(); runtime_role text;
BEGIN
  IF NOT (target_schema='public' OR target_schema ~ '^meridian_test_[0-9a-f]{32}$')
  THEN RAISE EXCEPTION 'Snapshot access requires reviewed schema'; END IF;
  runtime_role := 'meridian_bff_' || target_schema;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=runtime_role AND NOT
    (rolsuper OR rolcreatedb OR rolcreaterole OR rolinherit OR rolreplication OR rolbypassrls))
  THEN RAISE EXCEPTION 'Snapshot access requires restricted runtime role'; END IF;
  IF EXISTS (SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=runtime_role))
  THEN RAISE EXCEPTION 'Snapshot runtime must not inherit roles'; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    EXECUTE format('REVOKE ALL ON TABLE %I.broker_snapshots FROM anon', target_schema);
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    EXECUTE format('REVOKE ALL ON TABLE %I.broker_snapshots FROM authenticated', target_schema);
  END IF;
  EXECUTE format('GRANT SELECT ON %I.broker_snapshots TO %I', target_schema, runtime_role);
  EXECUTE format('CREATE POLICY meridian_snapshot_read ON %I.broker_snapshots FOR SELECT TO %I USING (account_id = %L)', target_schema, runtime_role, 'shared-isa');
END $snapshot_access$;

UPDATE alembic_version SET version_num='0006' WHERE version_num='0005';
