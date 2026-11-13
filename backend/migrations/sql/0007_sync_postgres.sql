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
