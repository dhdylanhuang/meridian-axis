"""Synthetic DBAPI transport check; temporary data cannot prove durable imports."""

NUMERIC_TEXT = "1.55000000000000000000001240"
TIMESTAMP_TEXT = "2026-01-02T12:34:56.123456Z"


class _ProbeFailure(Exception):
    pass


def run_database_probe(connect) -> dict:
    """Own a fresh DBAPI connection; return fixed diagnostics without driver text."""
    connection = cursor = None
    result = {"status": "failed", "error_code": "connection_failed"}
    stage = "connection_failed"
    try:
        connection = connect()
        cursor = connection.cursor()
        stage = "transaction_failed"
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        cursor.execute(
            "CREATE TEMP TABLE meridian_transport_probe "
            "(id INTEGER PRIMARY KEY, amount NUMERIC NOT NULL, observed_at TIMESTAMPTZ NOT NULL) "
            "ON COMMIT DROP"
        )
        cursor.execute(
            "INSERT INTO meridian_transport_probe VALUES "
            "(1, 1.55000000000000000000001240, '2026-01-02T12:34:56.123456Z')"
        )
        cursor.execute("SAVEPOINT synthetic_failure")
        cursor.execute(
            "INSERT INTO meridian_transport_probe VALUES "
            "(2, 2.00000000000000000000000001, '2026-01-02T12:34:56.654321Z')"
        )
        stage = "integrity_check_failed"
        try:
            cursor.execute(
                "INSERT INTO meridian_transport_probe VALUES (1, 3, '2026-01-02T12:34:56.123456Z')"
            )
        except Exception as error:
            fields = error.args[0] if error.args else None
            if not isinstance(fields, dict) or fields.get("C") != "23505":
                raise _ProbeFailure from None
        else:
            raise _ProbeFailure
        stage = "transaction_failed"
        cursor.execute("ROLLBACK TO SAVEPOINT synthetic_failure")
        cursor.execute("RELEASE SAVEPOINT synthetic_failure")
        cursor.execute(
            "SELECT id, amount::text, "
            "to_char(observed_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
            "FROM meridian_transport_probe ORDER BY id"
        )
        stage = "value_mismatch"
        if [tuple(row) for row in cursor.fetchall()] != [(1, NUMERIC_TEXT, TIMESTAMP_TEXT)]:
            raise _ProbeFailure
        stage = "commit_failed"
        connection.commit()
        stage = "temporary_cleanup_failed"
        cursor.execute("SELECT to_regclass('pg_temp.meridian_transport_probe') IS NULL")
        cleanup = cursor.fetchone()
        if cleanup is None or len(cleanup) != 1 or cleanup[0] is not True:
            raise _ProbeFailure
        connection.rollback()  # End the read transaction opened by the cleanup check.
        result = {
            "status": "ok",
            "exact_numeric": NUMERIC_TEXT,
            "timestamp_utc": TIMESTAMP_TEXT,
            "accepted_rows": 1,
            "rolled_back_rows": 1,
            "temporary_table_removed": True,
            "durable_commit_verified": False,
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
