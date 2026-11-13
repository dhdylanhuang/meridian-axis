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
