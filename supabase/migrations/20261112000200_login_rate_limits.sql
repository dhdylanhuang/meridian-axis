-- Closed login-rate counter foundation, matching Alembic parity 0004.
-- No account, login bucket, credential, function, policy or role is seeded.
-- The managed runner owns the transaction and reviewed search_path.

CREATE TABLE login_rate_limits (
	bucket VARCHAR(64) NOT NULL,
	window_started_at BIGINT NOT NULL,
	attempts INTEGER NOT NULL,
	PRIMARY KEY (bucket),
	CONSTRAINT ck_login_bucket_length CHECK (length(bucket) BETWEEN 1 AND 64),
	CONSTRAINT ck_login_window_nonnegative CHECK (window_started_at >= 0),
	CONSTRAINT ck_login_attempts_range CHECK (attempts BETWEEN 1 AND 1000)
);

DO $meridian_closed_login_rate$
DECLARE
    api_role text;
BEGIN
    IF (SELECT count(*) FROM alembic_version) <> 1
       OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE version_num = '0003') THEN
        RAISE EXCEPTION 'Expected schema parity 0003 before login-rate migration';
    END IF;
    ALTER TABLE login_rate_limits ENABLE ROW LEVEL SECURITY;
    REVOKE ALL PRIVILEGES ON TABLE login_rate_limits FROM PUBLIC;
    FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = api_role) THEN
            EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE login_rate_limits FROM '
                || pg_catalog.quote_ident(api_role);
        END IF;
    END LOOP;
    UPDATE alembic_version SET version_num = '0004' WHERE version_num = '0003';
END;
$meridian_closed_login_rate$;
