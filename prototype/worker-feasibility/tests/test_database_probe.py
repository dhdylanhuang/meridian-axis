"""Offline DBAPI lifecycle checks; these do not exercise a PostgreSQL server."""

import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "database_probe", Path(__file__).resolve().parents[1] / "src/database_probe.py"
)
probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe)


class FakeConnection:
    def __init__(self, failure=None, code="23505"):
        self.failure, self.code = failure, code
        self.events = []
        self.statements = []

    def cursor(self):
        self.events.append("cursor")
        if self.failure == "cursor":
            raise RuntimeError("private-connection")
        return FakeCursor(self)

    def commit(self):
        self.events.append("commit")
        if self.failure == "commit":
            raise RuntimeError("private-commit")

    def rollback(self):
        self.events.append("rollback")
        if self.failure == "rollback":
            raise RuntimeError("private-rollback")

    def close(self):
        self.events.append("connection.close")
        if self.failure == "close":
            raise RuntimeError("private-close")


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement):
        connection = self.connection
        connection.statements.append(statement)
        if connection.failure == "execute":
            raise RuntimeError("private-sql")
        if "(1, 3," in statement:
            if connection.failure == "no_conflict":
                return
            raise RuntimeError({"C": connection.code, "M": "private-driver-payload"})

    def fetchall(self):
        if self.connection.failure in ("values", "rollback"):
            return [(2, "private-value", "private-time")]
        return [[1, "1.55000000000000000000001240", "2026-01-02T12:34:56.123456Z"]]

    def fetchone(self):
        return (self.connection.failure != "cleanup",)

    def close(self):
        self.connection.events.append("cursor.close")
        if self.connection.failure == "cursor_close":
            raise RuntimeError("private-cursor")


class DatabaseProbeTests(unittest.TestCase):
    def test_success_commits_then_checks_temp_cleanup_and_closes(self):
        connection = FakeConnection()
        result = probe.run_database_probe(lambda connection=connection: connection)
        self.assertEqual(result["status"], "ok")
        self.assertIs(result["durable_commit_verified"], False)
        self.assertEqual(result["accepted_rows"], 1)
        self.assertEqual(result["rolled_back_rows"], 1)
        self.assertEqual(result["exact_numeric"], "1.55000000000000000000001240")
        self.assertEqual(result["timestamp_utc"], "2026-01-02T12:34:56.123456Z")
        self.assertEqual(
            connection.events,
            ["cursor", "commit", "rollback", "cursor.close", "connection.close"],
        )
        self.assertIn("ON COMMIT DROP", connection.statements[1])
        self.assertIn("ROLLBACK TO SAVEPOINT synthetic_failure", connection.statements)
        self.assertTrue(connection.statements[-1].startswith("SELECT to_regclass"))

    def test_connection_error_is_safe(self):
        def fail():
            raise RuntimeError("private-password")

        self.assertEqual(
            probe.run_database_probe(fail),
            {"status": "failed", "error_code": "connection_failed"},
        )

    def test_failures_rollback_close_and_never_return_private_values(self):
        for failure, expected in (
            ("cursor", "connection_failed"),
            ("execute", "transaction_failed"),
            ("values", "value_mismatch"),
            ("commit", "commit_failed"),
            ("cleanup", "temporary_cleanup_failed"),
            ("no_conflict", "integrity_check_failed"),
            ("rollback", "rollback_failed"),
            ("close", "close_failed"),
            ("cursor_close", "close_failed"),
        ):
            with self.subTest(failure=failure):
                connection = FakeConnection(failure=failure)
                result = probe.run_database_probe(lambda connection=connection: connection)
                self.assertEqual(result, {"status": "failed", "error_code": expected})
                self.assertEqual(connection.events[-1], "connection.close")
                self.assertIn("rollback", connection.events)
                self.assertNotIn("private", repr(result))

    def test_only_exact_unique_violation_sqlstate_is_accepted(self):
        for code in ("23503", "23505 private", None):
            with self.subTest(code=code):
                connection = FakeConnection(code=code)
                self.assertEqual(
                    probe.run_database_probe(lambda connection=connection: connection),
                    {"status": "failed", "error_code": "integrity_check_failed"},
                )
                self.assertNotIn("commit", connection.events)
                self.assertIn("rollback", connection.events)
