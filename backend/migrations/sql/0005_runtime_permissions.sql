-- Immutable 0005 DCL shared with the native hosted asset; no parity marker writer.
-- This role has no password until separate private credential provisioning.
DO $meridian_runtime_permissions$
DECLARE
    target_schema text := pg_catalog.current_schema();
    runtime_role text;
    active_session text;
    session_audit text;
BEGIN
    IF target_schema IS NULL OR NOT (
        target_schema = 'public' OR target_schema ~ '^meridian_test_[0-9a-f]{32}$'
    ) THEN
        RAISE EXCEPTION 'Runtime permissions require the reviewed application schema';
    END IF;
    runtime_role := 'meridian_bff_' || target_schema;
    IF pg_catalog.octet_length(runtime_role) > 63 THEN
        RAISE EXCEPTION 'Runtime role identifier is too long';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = current_user AND (rolsuper OR rolcreaterole)
    ) THEN
        RAISE EXCEPTION 'Runtime permissions require a role administrator';
    END IF;

    -- A collision fails; an unknown existing role is never adopted or hardened
    -- in place. The surrounding migration transaction owns the entire change.
    EXECUTE pg_catalog.format(
        'CREATE ROLE %I LOGIN PASSWORD NULL NOSUPERUSER NOCREATEDB NOCREATEROLE '
        || 'NOINHERIT NOBYPASSRLS', runtime_role
    );
    EXECUTE pg_catalog.format('GRANT USAGE ON SCHEMA %I TO %I', target_schema, runtime_role);
    -- USAGE must not inherit CREATE through an existing PUBLIC schema ACL.
    -- A mismatch fails atomically; this migration never rewrites unrelated ACLs.
    IF pg_catalog.has_schema_privilege(runtime_role, target_schema, 'CREATE') THEN
        RAISE EXCEPTION 'Runtime role must not have schema creation privileges';
    END IF;
    EXECUTE pg_catalog.format(
        'GRANT SELECT ON %I.account_members, %I.app_sessions TO %I',
        target_schema, target_schema, runtime_role
    );
    EXECUTE pg_catalog.format(
        'GRANT INSERT ON %I.app_sessions, %I.audit_log TO %I',
        target_schema, target_schema, runtime_role
    );
    EXECUTE pg_catalog.format('GRANT UPDATE (revoked_at) ON %I.app_sessions TO %I',
        target_schema, runtime_role);
    EXECUTE pg_catalog.format('GRANT SELECT, INSERT ON %I.login_rate_limits TO %I',
        target_schema, runtime_role);
    EXECUTE pg_catalog.format(
        'GRANT UPDATE (window_started_at, attempts) ON %I.login_rate_limits TO %I',
        target_schema, runtime_role
    );

    EXECUTE pg_catalog.format($policy$
        CREATE POLICY meridian_member_read ON %I.account_members FOR SELECT TO %I
        USING (account_id = %L AND revoked_at IS NULL
            AND created_at::timestamptz <= pg_catalog.statement_timestamp())
    $policy$, target_schema, runtime_role, 'shared-isa');

    active_session := pg_catalog.format($condition$
        account_id = %L AND EXISTS (
            SELECT 1 FROM %I.account_members m
            WHERE m.account_id = app_sessions.account_id
              AND m.auth_subject = app_sessions.auth_subject
              AND m.revoked_at IS NULL
              AND m.created_at::timestamptz <= pg_catalog.statement_timestamp()
        )
    $condition$, 'shared-isa', target_schema);
    -- Revoked rows remain readable: PostgreSQL applies SELECT visibility to
    -- UPDATE too, including a newly revoked row. Only the service consumes it.
    EXECUTE pg_catalog.format(
        'CREATE POLICY meridian_session_read ON %I.app_sessions '
        || 'FOR SELECT TO %I USING (%s)', target_schema, runtime_role, active_session
    );
    EXECUTE pg_catalog.format(
        'CREATE POLICY meridian_session_insert ON %I.app_sessions '
        || 'FOR INSERT TO %I WITH CHECK (%s)', target_schema, runtime_role, active_session
    );
    EXECUTE pg_catalog.format(
        'CREATE POLICY meridian_session_revoke ON %I.app_sessions '
        || 'FOR UPDATE TO %I USING ((%s) AND revoked_at IS NULL) WITH CHECK (%s)',
        target_schema, runtime_role, active_session, active_session
    );
    session_audit := pg_catalog.format($condition$
        entity_id = %L AND entity_type = 'account' AND run_id IS NULL
        AND details_json = '{}'
        AND action IN ('session_login', 'session_rotate', 'session_logout')
        AND EXISTS (
            SELECT 1 FROM %I.account_members m
            WHERE m.account_id = audit_log.entity_id
              AND m.auth_subject = audit_log.actor
              AND m.revoked_at IS NULL
              AND m.created_at::timestamptz <= pg_catalog.statement_timestamp()
        )
    $condition$, 'shared-isa', target_schema);
    EXECUTE pg_catalog.format(
        'CREATE POLICY meridian_session_audit ON %I.audit_log '
        || 'FOR INSERT TO %I WITH CHECK (%s)', target_schema, runtime_role, session_audit
    );
    EXECUTE pg_catalog.format(
        'CREATE POLICY meridian_login_read ON %I.login_rate_limits '
        || 'FOR SELECT TO %I USING (bucket = %L)', target_schema, runtime_role, 'shared-login'
    );
    EXECUTE pg_catalog.format(
        'CREATE POLICY meridian_login_insert ON %I.login_rate_limits '
        || 'FOR INSERT TO %I WITH CHECK (bucket = %L)', target_schema, runtime_role, 'shared-login'
    );
    EXECUTE pg_catalog.format(
        'CREATE POLICY meridian_login_update ON %I.login_rate_limits '
        || 'FOR UPDATE TO %I USING (bucket = %L) WITH CHECK (bucket = %L)',
        target_schema, runtime_role, 'shared-login', 'shared-login'
    );
END;
$meridian_runtime_permissions$;
