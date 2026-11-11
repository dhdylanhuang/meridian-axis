-- Great Dyke Meridian: hosted evidence foundation.
-- DDL origin: backend SQLAlchemy models, matching Alembic head 0002.
-- Hosted migrations have one writer: Supabase migration history. The Alembic
-- marker below records parity; it is not permission to run a second migrator.
-- The managed runner owns the transaction and a trusted search_path (public in
-- the dedicated hosted project). Tests execute this unchanged asset only in an
-- isolated generated schema. No explicit transaction control is embedded here.
-- Existing table names deliberately fail; unknown schemas are never adopted.
-- No account, financial source row, login, Auth membership or policy is seeded.


CREATE TABLE accounts (
	id VARCHAR(64) NOT NULL,
	environment VARCHAR(8) NOT NULL,
	broker VARCHAR(32) NOT NULL,
	wrapper VARCHAR(32) NOT NULL,
	currency VARCHAR(3) NOT NULL,
	private_reference TEXT,
	PRIMARY KEY (id),
	CONSTRAINT ck_account_environment CHECK (environment IN ('demo', 'live')),
	CONSTRAINT ck_account_currency CHECK (length(currency) = 3 AND currency = upper(currency))
);

CREATE TABLE import_log (
	id VARCHAR(64) NOT NULL,
	account_id VARCHAR(64) NOT NULL,
	kind VARCHAR(64) NOT NULL,
	status VARCHAR(16) NOT NULL,
	content_hash VARCHAR(64),
	started_at TEXT NOT NULL,
	finished_at TEXT,
	error_code VARCHAR(64),
	counts_json TEXT DEFAULT '{}' NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_import_id_account UNIQUE (id, account_id),
	CONSTRAINT ck_import_status CHECK (status IN ('running', 'succeeded', 'failed', 'duplicate')),
	CONSTRAINT ck_import_hash_length CHECK (content_hash IS NULL OR length(content_hash) = 64),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE INDEX ix_import_account_started ON import_log (account_id, started_at);

CREATE UNIQUE INDEX uq_import_accepted_hash ON import_log (account_id, kind, content_hash) WHERE status = 'succeeded' AND content_hash IS NOT NULL;

CREATE TABLE audit_log (
	id VARCHAR(64) NOT NULL,
	occurred_at TEXT NOT NULL,
	actor VARCHAR(64) NOT NULL,
	action VARCHAR(64) NOT NULL,
	entity_type VARCHAR(64) NOT NULL,
	entity_id VARCHAR(64) NOT NULL,
	run_id VARCHAR(64),
	details_json TEXT DEFAULT '{}' NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(run_id) REFERENCES import_log (id)
);

CREATE INDEX ix_audit_occurred ON audit_log (occurred_at);

CREATE TABLE source_records (
	id VARCHAR(64) NOT NULL,
	run_id VARCHAR(64) NOT NULL,
	account_id VARCHAR(64) NOT NULL,
	kind VARCHAR(64) NOT NULL,
	row_number INTEGER,
	schema_version VARCHAR(64) NOT NULL,
	payload_json TEXT NOT NULL,
	digest VARCHAR(64) NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_source_run_account FOREIGN KEY(run_id, account_id) REFERENCES import_log (id, account_id),
	CONSTRAINT uq_source_run_row UNIQUE (run_id, row_number),
	CONSTRAINT ck_source_row_positive CHECK (row_number IS NULL OR row_number > 0),
	CONSTRAINT ck_source_digest_length CHECK (length(digest) = 64),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE INDEX ix_source_account_kind ON source_records (account_id, kind);

CREATE TABLE alembic_version (
	version_num VARCHAR(32) NOT NULL,
	CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INSERT INTO alembic_version (version_num) VALUES ('0002');

-- Close the data surface before the runner commits. Owners and BYPASSRLS
-- roles retain their PostgreSQL powers. Runtime membership/authorization and
-- least-privilege access remain a separate gate; there are no invented policies.
-- Source/audit immutability still guards ordinary ORM updates, not owner SQL.
DO $meridian_private_tables$
DECLARE
    target_table text;
    api_role text;
BEGIN
    FOREACH target_table IN ARRAY ARRAY[
        'accounts', 'import_log', 'source_records', 'audit_log', 'alembic_version'
    ] LOOP
        EXECUTE 'ALTER TABLE ' || pg_catalog.quote_ident(target_table)
            || ' ENABLE ROW LEVEL SECURITY';
        EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE ' || pg_catalog.quote_ident(target_table)
            || ' FROM PUBLIC';
        FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
            IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = api_role) THEN
                EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE ' || pg_catalog.quote_ident(target_table)
                    || ' FROM ' || pg_catalog.quote_ident(api_role);
            END IF;
        END LOOP;
    END LOOP;
END;
$meridian_private_tables$;
