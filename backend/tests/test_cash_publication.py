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
