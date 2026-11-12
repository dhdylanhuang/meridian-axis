-- Closed membership/session foundation, matching Alembic parity 0003.
-- No identity, member, session, policy, runtime role or credential is seeded.
-- The managed runner owns the transaction and reviewed search_path.
-- Existing evidence/bootstrap migrations are immutable.


CREATE TABLE account_members (
	account_id VARCHAR(64) NOT NULL,
	auth_subject VARCHAR(36) NOT NULL,
	slot INTEGER NOT NULL,
	created_at TEXT NOT NULL,
	revoked_at TEXT,
	PRIMARY KEY (account_id, auth_subject),
	CONSTRAINT ck_member_slot CHECK (slot IN (1, 2)),
	CONSTRAINT ck_member_subject_length CHECK (length(auth_subject) = 36),
	FOREIGN KEY(account_id) REFERENCES accounts (id)
);

CREATE UNIQUE INDEX uq_member_active_slot ON account_members (account_id, slot) WHERE revoked_at IS NULL;

CREATE TABLE app_sessions (
	token_hash VARCHAR(64) NOT NULL,
	account_id VARCHAR(64) NOT NULL,
	auth_subject VARCHAR(36) NOT NULL,
	csrf_hash VARCHAR(64) NOT NULL,
	created_at TEXT NOT NULL,
	expires_at TEXT NOT NULL,
	revoked_at TEXT,
	PRIMARY KEY (token_hash),
	CONSTRAINT fk_session_account_member FOREIGN KEY(account_id, auth_subject) REFERENCES account_members (account_id, auth_subject),
	CONSTRAINT ck_session_token_hash_length CHECK (length(token_hash) = 64),
	CONSTRAINT ck_session_csrf_hash_length CHECK (length(csrf_hash) = 64),
	CONSTRAINT ck_session_expiry CHECK (expires_at > created_at)
);

DO $meridian_closed_auth$
DECLARE
    target_table text;
    api_role text;
BEGIN
    IF (SELECT count(*) FROM alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE version_num = '0002') THEN
        RAISE EXCEPTION 'Expected schema parity 0002 before membership/session migration';
    END IF;
    FOREACH target_table IN ARRAY ARRAY['account_members', 'app_sessions'] LOOP
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
    UPDATE alembic_version SET version_num = '0003' WHERE version_num = '0002';
END;
$meridian_closed_auth$;
