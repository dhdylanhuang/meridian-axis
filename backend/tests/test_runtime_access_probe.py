"""Offline DBAPI behavior checks; an admin SET ROLE cannot prove a real login."""

import importlib.util
from pathlib import Path

import pytest

_SOURCE = (
    Path(__file__).resolve().parents[2] / "prototype/worker-feasibility/src/runtime_access_probe.py"
)
_SPEC = importlib.util.spec_from_file_location("runtime_access_probe", _SOURCE)
probe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(probe)


class FakeConnection:
    def __init__(self, *, failure=None, identity=None, denial_code="42501"):
        self.failure = failure
        self.identity = identity or ("meridian_bff_public",) + (False,) * 7
        self.denial_code = denial_code
        self.statements = []
        self.events = []
        self.count = 0
        self.row = None
        self.cursor_instance = FakeCursor(self)

    def cursor(self):
        self.events.append("cursor")
        return self.cursor_instance

    def rollback(self):
        self.events.append("rollback")
        if self.failure == "rollback":
            raise RuntimeError("private-driver-rollback")
        if self.failure != "residual":
            self.count = 0

    def commit(self):
        pytest.fail("The runtime access diagnostic must never commit")

    def close(self):
        self.events.append("connection.close")
        if self.failure == "close":
            raise RuntimeError("private-driver-close")


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql):
        db = self.connection
        db.statements.append(sql)
        if sql == probe._ROLE_QUERY:
            self.row = db.identity
        elif sql.startswith("SELECT * FROM public."):
            if db.failure != "allowed":
                raise RuntimeError({"C": db.denial_code, "M": "private-driver-detail"})
        elif sql.startswith("SET LOCAL ROLE"):
            if db.failure != "role_allowed":
                raise RuntimeError({"C": db.denial_code, "M": "private-driver-detail"})
        elif sql.startswith("DELETE FROM"):
            if db.failure != "delete_allowed":
                raise RuntimeError({"C": db.denial_code, "M": "private-driver-detail"})
        elif "runtime-access-forbidden" in sql:
            if db.failure != "foreign_allowed":
                raise RuntimeError({"C": db.denial_code, "M": "private-driver-detail"})
        elif sql == probe._COUNT_QUERY:
            self.row = (1 if db.failure == "existing" else db.count,)
        elif sql.startswith("INSERT INTO public.login_rate_limits"):
            if db.failure == "insert":
                raise RuntimeError("private-driver-insert")
            db.count = 1
        elif sql.startswith("SELECT attempts"):
            self.row = (2 if db.failure == "wrong_count" else db.count,)

    def fetchone(self):
        return self.row

    def close(self):
        self.connection.events.append("cursor.close")
        if self.connection.failure == "cursor_close":
            raise RuntimeError("private-cursor-close")


def test_runtime_probe_checks_denials_rolls_back_counter_and_never_commits():
    connection = FakeConnection()
    result = probe.run_runtime_access_probe(lambda: connection)
    assert all(
        sql.endswith("LIMIT 0")
        for sql in connection.statements
        if sql.startswith("SELECT * FROM public.")
    )
    assert result == {
        "status": "ok",
        "identity_verified": True,
        "forbidden_selects_denied": True,
        "role_escalation_denied": True,
        "foreign_bucket_denied": True,
        "counter_delete_denied": True,
        "counter_write_rolled_back": True,
    }
    assert connection.count == 0
    assert connection.events == [
        "cursor",
        "rollback",
        "rollback",
        "cursor.close",
        "connection.close",
    ]
    assert connection.statements.count("SAVEPOINT meridian_permission_denial") == 7
    assert connection.statements.count("ROLLBACK TO SAVEPOINT meridian_permission_denial") == 7
    assert connection.statements.count("RELEASE SAVEPOINT meridian_permission_denial") == 7
    assert connection.statements.count("SET LOCAL statement_timeout = '3s'") == 2


@pytest.mark.parametrize(
    "identity",
    [
        ("postgres",) + (False,) * 7,
        ("meridian_bff_public", True) + (False,) * 6,
        ("meridian_bff_public",) + (False,) * 6 + (True,),
        ("meridian_bff_public",) + (0,) * 7,
    ],
)
def test_wrong_or_elevated_role_stops_before_any_table_statement(identity):
    connection = FakeConnection(identity=identity)
    assert probe.run_runtime_access_probe(lambda: connection) == {
        "status": "failed",
        "error_code": "identity_failed",
    }
    assert connection.statements == [probe._ROLE_QUERY]
    assert connection.events[-2:] == ["cursor.close", "connection.close"]


@pytest.mark.parametrize(
    "failure,code",
    [
        ("allowed", "forbidden_select_allowed"),
        ("role_allowed", "role_escalation_allowed"),
        ("foreign_allowed", "foreign_bucket_allowed"),
        ("delete_allowed", "counter_delete_allowed"),
        ("existing", "counter_not_empty"),
        ("insert", "counter_write_failed"),
        ("wrong_count", "counter_write_failed"),
        ("residual", "counter_rollback_unverified"),
        ("rollback", "rollback_failed"),
        ("close", "close_failed"),
        ("cursor_close", "close_failed"),
    ],
)
def test_runtime_probe_failures_are_redacted_and_resources_close(failure, code):
    connection = FakeConnection(failure=failure)
    result = probe.run_runtime_access_probe(lambda: connection)
    assert result == {"status": "failed", "error_code": code}
    assert "private" not in repr(result)
    assert connection.events[-1] == "connection.close"


@pytest.mark.parametrize("code", ["23505", "42P01", None])
def test_only_insufficient_privilege_is_permission_denial(code):
    connection = FakeConnection(denial_code=code)
    assert probe.run_runtime_access_probe(lambda: connection) == {
        "status": "failed",
        "error_code": "forbidden_select_allowed",
    }
    assert not any(sql.startswith("INSERT") for sql in connection.statements)


def test_connection_failure_never_echoes_driver_text():
    def connect():
        raise RuntimeError("private-database-password")

    assert probe.run_runtime_access_probe(connect) == {
        "status": "failed",
        "error_code": "connection_failed",
    }
