"""Synthetic offline quantity diagnostics; no live history or financial inputs."""

import asyncio
import copy
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_broker_ingestion import NOW, capture_document, encoded, ingest
from test_broker_ingestion import engine as engine
from test_broker_sync import API

from meridian.adapters.broker_evidence import validate_capture
from meridian.application.broker_jobs import BrokerJobs
from meridian.application.broker_sync import BrokerSync
from meridian.application.history_reconciliation import (
    ReconciliationError,
    _record,
    history_reconciliation,
)
from meridian.application.snapshot_publish import publish_snapshot
from meridian.domain.quantity_history import reconcile_quantities
from meridian.reconcile_history import main


def seed(engine):
    report = ingest(engine)
    assert report.status == "succeeded"
    with Session(engine) as db, db.begin():
        publish_snapshot(
            db,
            account_id="shared-isa",
            run_id=report.run_id,
            evidence=validate_capture(encoded()),
            now=NOW,
        )


def read(engine):
    with Session(engine) as db:
        return history_reconciliation(db, account_id="shared-isa")


def test_capture_report_preserves_precision_corporate_actions_and_no_fill(engine):
    seed(engine)
    report = read(engine)
    assert report["quantities"] == [
        {
            "ticker": "SYNTH",
            "unit": "instrument_units",
            "known_trade_quantity": "0.125000000000000000000001",
            "broker_quantity": "1.125000000000000000000001",
            "unexplained_difference": "1",
            "state": "difference",
        }
    ]
    records = {r["identity"]: r for r in report["records"]}
    assert records["fill:synthetic-split"]["state"] == "corporate_action_review"
    assert records["fill:synthetic-split"]["quantity_delta"] is None
    assert records["order:synthetic-cancelled"]["state"] == "no_execution"
    assert report["cash"]["availability"] == "unsupported"
    assert report["coverage"]["lifetime"] == "unverified"
    assert report["availability"] == "provisional"
    assert read(engine) == report


def test_complete_revision_replaces_effect_and_partial_pages_stay_out(engine):
    seed(engine)
    clock = [NOW + timedelta(hours=1)]
    api = API()
    jobs = BrokerJobs(engine, "shared-isa", clock=lambda: clock[0], random_value=lambda: 1)
    sync = BrokerSync(engine, "shared-isa", "live", "synthetic-broker", api, jobs=jobs)
    rows = api.rows["orders"]["records"]
    api.pages = [(rows, None)]
    assert asyncio.run(sync.history_page("orders"))["status"] == "succeeded"
    report = read(engine)
    trade = next(r for r in report["records"] if r["identity"] == "fill:synthetic-fill")
    assert len(trade["evidence"]) == 2  # capture plus sync, one effect
    assert report["quantities"][0]["unexplained_difference"] == "1"
    clock[0] += timedelta(hours=1)
    api.pages = [(rows, None)]
    assert asyncio.run(sync.history_page("orders"))["status"] == "succeeded"
    assert read(engine)["coverage"]["revision_rows"] == 3
    clock[0] += timedelta(hours=1)
    revised = copy.deepcopy(rows)
    revised[0]["fill"]["quantity"] = "0.5"
    api.pages = [(revised, "/api/v0/equity/history/orders?cursor=2"), ([], None)]
    assert asyncio.run(sync.history_page("orders"))["status"] == "in_progress"
    partial = read(engine)
    assert partial["coverage"]["latest_order_sync_status"] == "running"
    assert partial["quantities"] == report["quantities"]
    assert asyncio.run(sync.history_page("orders"))["status"] == "succeeded"
    final = read(engine)
    assert final["quantities"][0]["known_trade_quantity"] == "0.5"
    assert final["quantities"][0]["unexplained_difference"] == "0.625000000000000000000001"
    trade = next(r for r in final["records"] if r["identity"] == "fill:synthetic-fill")
    assert len(trade["evidence"]) == 3
    assert trade["selected_revision_id"] == trade["evidence"][-1]["revision_id"]


def record():
    raw = capture_document()["observations"]["orders"]["records"][0]
    return _record(raw, source_id="source", observed_at=NOW)


@pytest.mark.parametrize(
    "side,quantity,state",
    [
        ("SELL", "-0.125000000000000000000001", "known_trade_delta"),
        ("SELL", "0.125", "quantity_sign_review"),
        ("BUY", "-0.125", "quantity_sign_review"),
        ("UNKNOWN", "0.125", "quantity_sign_review"),
    ],
)
def test_signed_quantity_policy_does_not_guess(side, quantity, state):
    sell = replace(record(), side=side, quantity=Decimal(quantity))
    result = reconcile_quantities([sell], {}, cutoff=NOW)
    assert result["records"][0]["state"] == state
    if state == "known_trade_delta":
        assert result["quantities"][0]["unexplained_difference"] == "0.125000000000000000000001"
    else:
        assert result["records"][0]["quantity_delta"] is None


def test_closed_holdings_future_fills_and_conflicting_observations():
    buy = record()
    sell = replace(buy, identity="fill:sell", fill_id="sell", side="SELL", quantity=-buy.quantity)
    result = reconcile_quantities([buy, sell], {}, cutoff=NOW)
    assert result["quantities"][0]["state"] == "matches_known_events_only"
    future = replace(buy, executed_at=NOW + timedelta(seconds=1))
    assert reconcile_quantities([future], {}, cutoff=NOW)["records"][0]["state"] == "after_snapshot"
    conflict = replace(buy, source_id="other", digest="different")
    result = reconcile_quantities([buy, conflict], {}, cutoff=NOW)
    assert result["records"][0]["state"] == "identity_conflict_review"
    assert result["records"][0]["quantity_delta"] is None


def test_scope_missing_snapshot_and_observation_limit_fail_closed(engine, monkeypatch):
    with Session(engine) as db:
        with pytest.raises(ReconciliationError, match="account_invalid"):
            history_reconciliation(db, account_id="other-account")
        with pytest.raises(ReconciliationError, match="snapshot_unavailable"):
            history_reconciliation(db, account_id="shared-isa")
    seed(engine)
    monkeypatch.setattr("meridian.application.history_reconciliation.MAX_OBSERVATIONS", 1)
    with pytest.raises(ReconciliationError, match="observation_limit"):
        read(engine)


def test_cli_reads_existing_database_without_writes_or_creation(engine, tmp_path, capsys):
    seed(engine)
    path = engine.url.database
    before = read(engine)
    assert main(["--database", path, "--account-id", "shared-isa"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report == before
    missing = tmp_path / "missing.sqlite3"
    assert main(["--database", str(missing), "--account-id", "shared-isa"]) == 2
    assert not missing.exists()
    assert "shared-isa" not in capsys.readouterr().err


def test_distinct_fills_under_one_order_are_not_merged():
    first = record()
    second = replace(first, identity="fill:second", fill_id="second", source_id="source2")
    report = reconcile_quantities([first, second], {}, cutoff=NOW)
    assert len(report["records"]) == 2
    assert report["quantities"][0]["known_trade_quantity"] == "0.250000000000000000000002"


@pytest.mark.parametrize(
    "table,column,error",
    [
        ("broker_snapshots", "snapshot_json", "snapshot_integrity_invalid"),
        ("source_records", "payload_json", "source_integrity_invalid"),
    ],
)
def test_tampered_evidence_fails_closed(engine, table, column, error):
    seed(engine)
    # Synthetic corruption bypasses ORM immutability solely to exercise read checks.
    with engine.begin() as connection:
        connection.execute(text(f"UPDATE {table} SET {column} = '{{}}'"))
    with pytest.raises(ReconciliationError, match=error):
        read(engine)
