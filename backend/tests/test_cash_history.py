"""Synthetic Python evidence boundary for the Rust cash core; no live calls."""

import asyncio
import json
import os
import subprocess
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_broker_ingestion import NOW
from test_broker_ingestion import engine as engine
from test_broker_sync import API
from test_history_reconciliation import seed

from meridian.application.broker_jobs import BrokerJobs
from meridian.application.broker_sync import BrokerSync
from meridian.application.cash_history import cash_history_request
from meridian.application.history_reconciliation import ReconciliationError
from meridian.export_cash_history import main


@pytest.fixture
def request_payload(engine):
    seed(engine)
    clock = [NOW + timedelta(hours=1)]
    api = API()
    rows = api.rows["transactions"]["records"]
    rows[0]["amount"] = "-0.2"
    jobs = BrokerJobs(engine, "shared-isa", clock=lambda: clock[0])
    service = BrokerSync(engine, "shared-isa", "live", "synthetic-broker", api, jobs=jobs)
    api.pages = [(rows, "/api/v0/equity/history/transactions?cursor=next"), ([], None)]
    assert asyncio.run(service.history_page("transactions"))["status"] == "in_progress"
    with Session(engine) as db:
        assert len(cash_history_request(db, account_id="shared-isa")["observations"]) == 1
    assert asyncio.run(service.history_page("transactions"))["status"] == "succeeded"
    with Session(engine) as db:
        return cash_history_request(db, account_id="shared-isa")


def test_export_preserves_revisions_and_keeps_signs_controls_unverified(request_payload):
    assert len(request_payload["observations"]) == 2
    assert {row["amount"] for row in request_payload["observations"]} == {"-0.1", "-0.2"}
    assert all(
        row["sign_basis"] == {"state": "unverified"} for row in request_payload["observations"]
    )
    assert request_payload["opening_cash"] == request_payload["closing_cash"] == []
    assert request_payload["broker_cash"]["available_to_trade"] == "70"
    assert request_payload["broker_cash"]["in_pies"] == "20"
    assert request_payload["broker_cash"]["reserved_for_orders"] == "5"


@pytest.mark.skipif(
    not os.environ.get("AXIS_RUST_TEST_BINARY"), reason="explicit native Rust build required"
)
def test_python_evidence_runs_through_native_rust_without_double_effect(request_payload):
    result = subprocess.run(
        [os.environ["AXIS_RUST_TEST_BINARY"]],
        input=json.dumps(request_payload),
        text=True,
        capture_output=True,
        timeout=10,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["method"] == "cash_reconciliation_rust_v1"
    assert len(report["records"]) == 1
    assert report["records"][0]["reported_amount"] == "-0.2"
    assert len(report["records"][0]["evidence"]) == 2
    assert report["records"][0]["state"] == "unverified_sign_review"
    assert report["cash"][0]["replayed_cash"] is None
    assert report["cash"][0]["unexplained_difference"] is None


def test_export_cli_is_read_only_and_refuses_missing_database(engine, tmp_path, capsys):
    seed(engine)
    assert main(["--database", engine.url.database, "--account-id", "shared-isa"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1
    missing = tmp_path / "missing.sqlite3"
    assert main(["--database", str(missing), "--account-id", "shared-isa"]) == 2
    assert not missing.exists()
    assert capsys.readouterr().err == "cash_history_export_failed\n"


def test_foreign_scope_and_tampered_source_fail_closed(engine):
    seed(engine)
    with Session(engine) as db, pytest.raises(ReconciliationError, match="account_invalid"):
        cash_history_request(db, account_id="foreign")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE source_records SET payload_json='{}' WHERE kind='trading212_transactions'")
        )
    with (
        Session(engine) as db,
        pytest.raises(ReconciliationError, match="source_integrity_invalid"),
    ):
        cash_history_request(db, account_id="shared-isa")
