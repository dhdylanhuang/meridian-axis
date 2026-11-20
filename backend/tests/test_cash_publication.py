"""Bounded Rust-to-approved-snapshot integration, entirely synthetic."""

import asyncio
import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from test_broker_ingestion import NOW
from test_broker_ingestion import engine as engine
from test_broker_sync import API
from test_history_reconciliation import seed

from meridian.application.broker_jobs import BrokerJobs
from meridian.application.broker_sync import BrokerSync
from meridian.application.cash_reconciliation import prepare_cash_summary
from meridian.application.snapshot_access import read_snapshot


@pytest.fixture
def driver(engine):
    seed(engine)
    clock = [NOW + timedelta(hours=1)]
    api = API()
    jobs = BrokerJobs(engine, "shared-isa", clock=lambda: clock[0])
    service = BrokerSync(engine, "shared-isa", "live", "synthetic-broker", api, jobs=jobs)
    api.pages = [(api.rows["transactions"]["records"], None)]
    assert asyncio.run(service.history_page("transactions"))["status"] == "succeeded"
    return service, clock


@pytest.mark.skipif(
    not os.environ.get("AXIS_NODE_TEST_BINARY"), reason="qualified generated WASM required"
)
def test_wasm_summary_commits_atomically_without_raw_history(driver):
    service, clock = driver
    active = []
    event.listen(service.engine, "begin", lambda connection: active.append(connection))
    event.listen(service.engine, "rollback", lambda connection: active.remove(connection))
    event.listen(service.engine, "commit", lambda connection: active.remove(connection))

    async def rpc(encoded):
        assert active == []  # release SQL transactions/connections before computation
        script = (
            Path(__file__).resolve().parents[2]
            / "prototype/worker-feasibility/tests/cash_summary_cli.mjs"
        )
        result = subprocess.run(
            [os.environ["AXIS_NODE_TEST_BINARY"], str(script)],
            input=encoded,
            text=True,
            capture_output=True,
            timeout=5,
            check=True,
        )
        return result.stdout

    service.cash_reconciler = rpc
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(service.engine) as db:
        snapshot = read_snapshot(db, "shared-isa")
        summary = snapshot["cash_reconciliation"]
        assert summary["method"] == "cash_reconciliation_rust_v1"
        assert summary["event_count"] == 1
        assert summary["observation_count"] == 1  # runtime deliberately excludes capture rows
        assert summary["review_counts"] == {"unverified_sign_review": 1}
        assert summary["activity_counts"] == {"WITHDRAW": 1}
        assert summary["cash"][0]["unexplained_difference"] is None
        assert summary["coverage"]["initial_capture"] == "not_included_runtime"
        assert "records" not in summary and "scope" not in summary
        assert "synthetic" not in json.dumps(summary)
        assert snapshot["total_value"] == "999.12345678901234567890123456789"
    # Failed broker refresh must not publish an orphan sidecar result or advance snapshot.
    clock[0] += timedelta(minutes=10)
    service.api.fail_positions = True
    assert asyncio.run(service.refresh())["status"] == "failed"
    with Session(service.engine) as db:
        assert read_snapshot(db, "shared-isa") == snapshot


@pytest.mark.parametrize("failure", ["rpc", "malformed", "limit"])
def test_sidecar_failure_never_blocks_broker_publication(driver, monkeypatch, failure):
    service, clock = driver

    async def rpc(encoded):
        if failure == "rpc":
            raise RuntimeError("private details must not escape")
        return '{"records":["private raw evidence"]}'

    service.cash_reconciler = rpc
    if failure == "limit":
        monkeypatch.setattr("meridian.application.cash_reconciliation.MAX_EVENTS", 0)
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(service.engine) as db:
        saved = read_snapshot(db, "shared-isa")
        summary = saved["cash_reconciliation"]
        assert summary["availability"] == ("unsupported" if failure == "limit" else "failed")
        assert summary["reason"] == (
            "history_limit" if failure == "limit" else "reconciliation_unavailable"
        )
        assert "private" not in json.dumps(summary)
        assert saved["total_value"] == "999.12345678901234567890123456789"


def test_missing_engine_is_explicit_and_does_not_read_history(driver):
    service, clock = driver
    with Session(service.engine) as db:
        projection = read_snapshot(db, "shared-isa")

    class NoDatabase:
        def connect(self):
            raise AssertionError("No engine means no extra evidence reads")

    result = asyncio.run(
        prepare_cash_summary(
            NoDatabase(),
            account_id="shared-isa",
            projection=projection,
            snapshot_id="pending",
            reconcile=None,
        )
    )
    assert result["availability"] == "unsupported"
    assert result["reason"] == "engine_not_configured"


def test_activity_projection_validates_counts_and_accepts_older_results():
    import hashlib

    from meridian.application.cash_reconciliation import approved_summary

    request = {
        "scope": {"account_id": "shared-isa", "environment": "live"},
        "cutoff": "2026-01-01T00:00:00Z",
        "broker_cash": {"snapshot_id": "pending", "currency": "GBP"},
        "observations": [{"currency": "GBP"}],
    }
    encoded = json.dumps(request)
    result = {
        "method": "cash_reconciliation_rust_v1",
        "scope": request["scope"],
        "availability": "provisional",
        "as_of": request["cutoff"],
        "source_snapshot_id": "pending",
        "input_revision": hashlib.sha256(encoded.encode()).hexdigest(),
        "event_count": 1,
        "observation_count": 1,
        "review_counts": {"unverified_sign_review": 1},
        "cash": [{"currency": "GBP", "state": "insufficient_data", "unexplained_difference": None}],
        "warnings": ["cash_signs_unverified"],
    }
    assert approved_summary(json.dumps(result), request, encoded)["activity_counts"] is None
    result["activity_counts"] = {"DEPOSIT": 1}
    assert approved_summary(json.dumps(result), request, encoded)["activity_counts"] == {
        "DEPOSIT": 1
    }
    for wrong in [{"DEPOSIT": 2}, {"private-provider-description": 1}, {"DEPOSIT": True}]:
        result["activity_counts"] = wrong
        with pytest.raises(ValueError, match="reconciliation_result_invalid"):
            approved_summary(json.dumps(result), request, encoded)


@pytest.mark.skipif(not os.environ.get("AXIS_NODE_TEST_BINARY"), reason="qualified WASM required")
def test_delivery_available_cash_window_and_projection_validation(driver):
    from sqlalchemy import select

    from meridian.application.cash_reconciliation import approved_summary
    from meridian.persistence.models import BrokerSnapshot

    service, clock = driver
    with Session(service.engine) as db:
        prior_id = db.scalar(select(BrokerSnapshot)).id
    clock[0] += timedelta(days=1)
    service.api.pages = [
        (
            [
                dict(
                    reference="new-interest",
                    type="INTEREST_ON_FREE_CASH",
                    amount="0.25",
                    currency="GBP",
                    dateTime="2026-01-02T12:00:00Z",
                ),
                dict(
                    reference="new-fee",
                    type="FEE",
                    amount="-1",
                    currency="GBP",
                    dateTime="2026-01-02T12:00:00Z",
                ),
            ],
            None,
        )
    ]
    assert asyncio.run(service.history_page("transactions"))["status"] == "succeeded"
    service.api.rows["account_summary"]["records"][0]["cash"]["availableToTrade"] = "70.25"
    captured = {}

    async def rpc(encoded):
        script = (
            Path(__file__).resolve().parents[2]
            / "prototype/worker-feasibility/tests/cash_summary_cli.mjs"
        )
        raw = subprocess.run(
            [os.environ["AXIS_NODE_TEST_BINARY"], str(script)],
            input=encoded,
            text=True,
            capture_output=True,
            timeout=5,
            check=True,
        ).stdout
        captured.update(encoded=encoded, raw=raw)
        return raw

    service.cash_reconciler = rpc
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(service.engine) as db:
        summary = read_snapshot(db, "shared-isa")["cash_reconciliation"]
    assert summary["availability"] == "provisional"
    assert summary["cash_sign_policy"] == "statement_checked_gbp_v1"
    # The old component check remains an explicit adapter capability, not a runtime query.
    from meridian.adapters.broker_evidence import canonical
    from meridian.application.cash_history import cash_history_request

    with Session(service.engine) as db:
        projection = read_snapshot(db, "shared-isa")
        request = cash_history_request(
            db,
            account_id="shared-isa",
            projection=projection,
            snapshot_id="window-control-test",
            include_captures=False,
            observed_available_cash=True,
            sign_policy="statement_checked_gbp_v1",
        )
    encoded = canonical(request)
    summary = approved_summary(asyncio.run(rpc(encoded)), request, encoded)
    window = summary["cash"][0]
    assert window["basis"] == "broker_available_to_trade"
    assert window["opening_source_snapshot_id"] == prior_id
    assert window["opening_balance"] == "70"
    assert window["closing_balance"] == "70.25"
    assert window["known_signed_movements"] == "0.25"
    assert window["unexplained_difference"] == "0"
    assert window["included_movement_count"] == 1
    assert window["excluded_movement_count"] == 1
    assert window["state"] == "matches_known_events_only"
    request = json.loads(captured["encoded"])
    raw = json.loads(captured["raw"])
    for key, wrong in [
        ("opening_balance", "0"),
        ("unexplained_difference", 0),
        ("opening_source_snapshot_id", "foreign"),
        ("excluded_movement_count", True),
    ]:
        invalid = json.loads(captured["raw"])
        invalid["cash"][0][key] = wrong
        with pytest.raises(ValueError):
            approved_summary(json.dumps(invalid), request, captured["encoded"])
    raw["cash_sign_policy"] = "invented-policy"
    with pytest.raises(ValueError):
        approved_summary(json.dumps(raw), request, captured["encoded"])


@pytest.mark.skipif(not os.environ.get("AXIS_NODE_TEST_BINARY"), reason="qualified WASM required")
def test_funding_totals_publish_dividends_and_cash_without_source_rows(driver):
    from meridian.application.cash_reconciliation import approved_summary

    service, clock = driver
    service.api.pages = [(service.api.rows["dividends"]["records"], None)]
    assert asyncio.run(service.history_page("dividends"))["status"] == "succeeded"
    captured = {}

    async def rpc(encoded):
        script = (
            Path(__file__).resolve().parents[2]
            / "prototype/worker-feasibility/tests/cash_summary_cli.mjs"
        )
        raw = subprocess.run(
            [os.environ["AXIS_NODE_TEST_BINARY"], str(script)],
            input=encoded,
            text=True,
            capture_output=True,
            timeout=5,
            check=True,
        ).stdout
        captured.update(encoded=encoded, raw=raw)
        return raw

    service.cash_reconciler = rpc
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(service.engine) as db:
        summary = read_snapshot(db, "shared-isa")["cash_reconciliation"]
    assert summary["event_count"] == 2  # equal references in different source families
    assert summary["coverage"]["families"] == ["cash_transactions", "paid_dividends"]
    activity = summary["reported_activity"]
    assert activity["since"] == "2026-01-01T00:00:00+00:00"
    assert {(r["category"], r["amount"]) for r in activity["totals"]} == {
        ("withdrawals", "-0.1"),
        ("dividends", "0.0123456789012345678901"),
    }
    assert all(row["unexplained_difference"] is None for row in summary["cash"])
    request = json.loads(captured["encoded"])
    assert request["opening_cash"] == []
    assert {r["family"] for r in request["observations"]} == {"transactions", "dividends"}
    assert "shared-ref" not in json.dumps(summary)
    for category, amount in [("unapproved", "1"), ("dividends", 1), ("dividends", "NaN")]:
        wrong = json.loads(captured["raw"])
        wrong["reported_activity"]["totals"][0].update(category=category, amount=amount)
        with pytest.raises(ValueError):
            approved_summary(json.dumps(wrong), request, captured["encoded"])
