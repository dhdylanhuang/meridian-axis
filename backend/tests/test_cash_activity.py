"""Synthetic on-demand rows, generation pinning and completed-history evidence."""

import asyncio
import json
import os
import subprocess
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session
from test_broker_ingestion import engine as engine
from test_cash_publication import driver as driver

from meridian.application.cash_activity import activity_query, cash_activity_page
from meridian.application.snapshot_access import read_snapshot


async def rpc(encoded):
    script = (
        Path(__file__).resolve().parents[2]
        / "prototype/worker-feasibility/tests/cash_summary_cli.mjs"
    )
    return subprocess.run(
        [os.environ["AXIS_NODE_TEST_BINARY"], str(script)],
        input=encoded,
        text=True,
        capture_output=True,
        timeout=5,
        check=True,
    ).stdout


@pytest.mark.skipif(not os.environ.get("AXIS_NODE_TEST_BINARY"), reason="qualified WASM required")
def test_detail_pages_match_saved_total_and_survive_later_revisions(driver):
    service, clock = driver
    clock[0] += timedelta(hours=1)
    withdrawals = [
        dict(
            reference="shared-ref",
            type="WITHDRAW",
            amount="-0.2",
            currency="GBP",
            dateTime="2026-01-01T01:00:00Z",
        )
    ]
    withdrawals += [
        dict(
            reference=f"withdrawal-{n:02}",
            type="WITHDRAW",
            amount="-1",
            currency="GBP",
            dateTime="2026-01-01T02:00:00Z",
        )
        for n in range(22)
    ]
    service.api.pages = [(withdrawals, None)]
    assert asyncio.run(service.history_page("transactions"))["status"] == "succeeded"
    payouts = service.api.rows["dividends"]["records"]
    payouts[0]["instrument"] = {"name": "Example issuer", "ticker": "EXAMPLE"}
    service.api.pages = [(payouts, None)]
    assert asyncio.run(service.history_page("dividends"))["status"] == "succeeded"
    service.cash_reconciler = rpc
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(service.engine) as db:
        summary = read_snapshot(db, "shared-isa")["cash_reconciliation"]
    assert all(
        row["state"] == "provider_history_traversed"
        for row in summary["history_coverage"]["families"]
    )
    assert summary["history_coverage"]["lifetime"] == "not_established"
    query = dict(
        snapshot_id=summary["source_snapshot_id"],
        input_revision=summary["input_revision"],
        category="withdrawals",
        currency="GBP",
        offset=0,
        limit=10,
    )
    # A later revision cannot change the inputs or rows behind an already-published total.
    clock[0] += timedelta(hours=1)
    changed = dict(withdrawals[0], amount="-0.3")
    service.api.pages = [([changed], None)]
    assert asyncio.run(service.history_page("transactions"))["status"] == "succeeded"
    rows = []
    for offset in (0, 10, 20):
        result, status = asyncio.run(
            cash_activity_page(service.engine, query | dict(offset=offset), rpc)
        )
        assert status == 200, result
        assert result["total_count"] == 23
        assert result["input_revision"] == query["input_revision"]
        rows.extend(result["entries"])
    assert len({row["reference"] for row in rows}) == len(rows) == 23
    total = next(
        row for row in summary["reported_activity"]["totals"] if row["category"] == "withdrawals"
    )
    assert (
        sum(Decimal(row["amount"]) for row in rows) == Decimal(total["amount"]) == Decimal("-22.2")
    )
    result, status = asyncio.run(
        cash_activity_page(service.engine, query | dict(category="dividends"), rpc)
    )
    assert status == 200 and result["entries"][0]["instrument_label"] == "Example issuer"
    assert result["entries"][0]["family"] == "dividends"
    assert result["entries"][0]["digest"] and result["entries"][0]["source_id"]
    assert "evidence" not in result["entries"][0]

    async def tampered(encoded):
        result = json.loads(await rpc(encoded))
        result["details"]["entries"][0]["source_id"] = "foreign-source"
        return json.dumps(result)

    result, status = asyncio.run(cash_activity_page(service.engine, query, tampered))
    assert status == 503 and result == {"error": "activity_unavailable"}
    for wrong in (dict(snapshot_id="missing"), dict(input_revision="a" * 64)):
        result, status = asyncio.run(cash_activity_page(service.engine, query | wrong, rpc))
        assert status == 409
    with pytest.raises(ValueError):
        activity_query(query | dict(limit=True))


@pytest.mark.skipif(not os.environ.get("AXIS_NODE_TEST_BINARY"), reason="qualified WASM required")
def test_unfinished_history_does_not_claim_coverage(driver):
    service, clock = driver
    service.api.pages = [
        (service.api.rows["dividends"]["records"], "/api/v0/equity/history/dividends?cursor=more")
    ]
    assert asyncio.run(service.history_page("dividends"))["status"] == "in_progress"
    service.cash_reconciler = rpc
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(service.engine) as db:
        summary = read_snapshot(db, "shared-isa")["cash_reconciliation"]
    by_family = {row["family"]: row for row in summary["history_coverage"]["families"]}
    assert by_family["dividends"]["state"] == "not_established"
    assert by_family["dividends"]["completed_at"] is None
    assert by_family["transactions"]["state"] == "provider_history_traversed"
    assert all(row["category"] != "dividends" for row in summary["reported_activity"]["totals"])
