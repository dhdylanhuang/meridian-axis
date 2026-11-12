"""Fixed, rollback-only qualification of an actual restricted database login."""

_ROLE_QUERY = (
    "SELECT current_user, r.rolsuper, r.rolcreatedb, r.rolcreaterole, "
    "r.rolinherit, r.rolreplication, r.rolbypassrls, "
    "EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.member = r.oid) "
    "FROM pg_catalog.pg_roles r WHERE r.rolname = current_user"
)
_COUNT_QUERY = "SELECT count(*) FROM public.login_rate_limits WHERE bucket = 'shared-login'"


class _ProbeFailure(Exception):
    pass


def _require_denial(cursor, statement):
    cursor.execute("SAVEPOINT meridian_permission_denial")
    try:
        cursor.execute(statement)
    except Exception as error:
        fields = error.args[0] if error.args else None
        if not isinstance(fields, dict) or fields.get("C") != "42501":
            raise _ProbeFailure from None
    else:
        raise _ProbeFailure
    cursor.execute("ROLLBACK TO SAVEPOINT meridian_permission_denial")
    cursor.execute("RELEASE SAVEPOINT meridian_permission_denial")


def _require_integer(cursor, expected):
    row = cursor.fetchone()
    if row is None or len(row) != 1 or type(row[0]) is not int or row[0] != expected:
        raise _ProbeFailure


def run_runtime_access_probe(connect) -> dict:
    """Require the real production role; never commit or inspect financial rows.

    This is deliberately not parameterized for a SET ROLE test surrogate:
    session_user can retain escalation powers even after current_user changes.
    The shared counter must be empty before this fresh-bootstrap diagnostic.
    """
    connection = cursor = None
    stage = "connection_failed"
    result = {"status": "failed", "error_code": stage}
    try:
        connection = connect()
        cursor = connection.cursor()
        stage = "identity_failed"
        cursor.execute(_ROLE_QUERY)
        identity = cursor.fetchone()
        if (
            identity is None
            or len(identity) != 8
            or identity[0] != "meridian_bff_public"
            or any(flag is not False for flag in identity[1:])
        ):
            raise _ProbeFailure
        cursor.execute("SET LOCAL statement_timeout = '3s'")
        stage = "forbidden_select_allowed"
        for table in ("accounts", "import_log", "source_records", "audit_log"):
            _require_denial(cursor, f"SELECT * FROM public.{table} LIMIT 0")
        stage = "role_escalation_allowed"
        _require_denial(cursor, "SET LOCAL ROLE postgres")
        stage = "foreign_bucket_allowed"
        _require_denial(
            cursor,
            "INSERT INTO public.login_rate_limits (bucket, window_started_at, attempts) "
            "VALUES ('runtime-access-forbidden', 0, 1)",
        )
        stage = "counter_delete_allowed"
        _require_denial(
            cursor, "DELETE FROM public.login_rate_limits WHERE bucket = 'shared-login'"
        )
        stage = "counter_not_empty"
        cursor.execute(_COUNT_QUERY)
        _require_integer(cursor, 0)
        stage = "counter_write_failed"
        cursor.execute(
            "INSERT INTO public.login_rate_limits (bucket, window_started_at, attempts) "
            "VALUES ('shared-login', "
            "pg_catalog.floor(EXTRACT(epoch FROM pg_catalog.statement_timestamp()))::bigint, 1)"
        )
        cursor.execute(
            "SELECT attempts FROM public.login_rate_limits WHERE bucket = 'shared-login'"
        )
        _require_integer(cursor, 1)
        stage = "rollback_failed"
        connection.rollback()
        stage = "counter_rollback_unverified"
        cursor.execute("SET LOCAL statement_timeout = '3s'")
        cursor.execute(_COUNT_QUERY)
        _require_integer(cursor, 0)
        connection.rollback()
        result = {
            "status": "ok",
            "identity_verified": True,
            "forbidden_selects_denied": True,
            "role_escalation_denied": True,
            "foreign_bucket_denied": True,
            "counter_delete_denied": True,
            "counter_write_rolled_back": True,
        }
    except Exception:
        result = {"status": "failed", "error_code": stage}
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                result["error_code"] = "rollback_failed"
    finally:
        for resource in (cursor, connection):
            if resource is not None:
                try:
                    resource.close()
                except Exception:
                    result = {"status": "failed", "error_code": "close_failed"}
    return result
