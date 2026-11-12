"""Exercise the unchanged Worker SQL control on disposable loopback PostgreSQL."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect
from test_postgres import postgres_schema as postgres_schema


@pytest.mark.postgres
def test_worker_database_probe_exact_values_savepoint_and_temporary_cleanup(postgres_schema):
    source = (
        Path(__file__).resolve().parents[2] / "prototype/worker-feasibility/src/database_probe.py"
    )
    spec = importlib.util.spec_from_file_location("worker_database_probe", source)
    assert spec is not None and spec.loader is not None
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)

    expected = {
        "status": "ok",
        "exact_numeric": "1.55000000000000000000001240",
        "timestamp_utc": "2026-01-02T12:34:56.123456Z",
        "accepted_rows": 1,
        "rolled_back_rows": 1,
        "temporary_table_removed": True,
        "durable_commit_verified": False,
    }
    # The reused fixture validates loopback, selects an empty generated schema
    # and uses NullPool. Each invocation owns a fresh DBAPI connection; no
    # application migration or permanent test table is needed by this control.
    for _ in range(2):
        assert probe.run_database_probe(postgres_schema.raw_connection) == expected
    assert inspect(postgres_schema).get_table_names() == []
