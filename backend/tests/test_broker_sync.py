"""Synthetic bounded refresh, durable pacing and resumable revision acceptance."""

import asyncio
import copy
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session
from test_broker_ingestion import NOW, capture_document
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_supabase_migration import native_engine as native_engine

from meridian.adapters.broker_evidence import (
    EvidenceError,
    canonical,
    validate_capture,
    validate_refresh,
)
from meridian.adapters.trading212 import PREFIX, BrokerError
from meridian.application.broker_jobs import BrokerJobs, Deferred
from meridian.application.broker_sync import BrokerSync, source_record
from meridian.application.snapshot_access import read_snapshot
from meridian.persistence.database import create_db_engine, upgrade_database
from meridian.persistence.models import (
    Account,
    BrokerEventRevision,
    BrokerSnapshot,
    BrokerSyncJob,
    ImportRun,
    SourceRecord,
)


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param("postgres_engine", marks=pytest.mark.postgres),
        pytest.param("native_engine", marks=pytest.mark.postgres),
    ]
)
def setup(tmp_path, request):
    if request.param == "sqlite":
        path = tmp_path / "sync.sqlite3"
        upgrade_database(path)
        engine = create_db_engine(path)
    else:
        engine = request.getfixturevalue(request.param)
    with Session(engine) as db, db.begin():
        db.add(Account(id="shared-isa", environment="live", private_reference="synthetic-broker"))
    clock = [NOW]
    jobs = BrokerJobs(engine, "shared-isa", clock=lambda: clock[0], random_value=lambda: 1)
    yield engine, clock, jobs
    if request.param == "sqlite":
        engine.dispose()


class API:
    environment = "live"

    def __init__(self):
        self.rows = copy.deepcopy(capture_document()["observations"])
        self.fail_positions = False
        self.pages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def account_summary(self):
        return SimpleNamespace(raw_payload=self.rows["account_summary"]["records"][0])

    async def positions(self):
        if self.fail_positions:
            raise BrokerError("transport_failure")
        return [SimpleNamespace(raw_payload=row) for row in self.rows["positions"]["records"]]

    async def history_page(self, family, path):
        rows, continuation = self.pages.pop(0)
        return [SimpleNamespace(raw_payload=row) for row in rows], continuation


def sync(setup, api):
    engine, clock, jobs = setup
    return BrokerSync(engine, "shared-isa", "live", "synthetic-broker", api, jobs=jobs)


def count(engine, model):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(model))


def test_refresh_contract_does_not_claim_empty_history():
    doc = capture_document()
    doc["version"] = 2
    doc["observations"] = {
        k: v for k, v in doc["observations"].items() if k in ("account_summary", "positions")
    }
    assert validate_refresh(canonical(doc).encode()).document == doc
    with pytest.raises(EvidenceError):
        validate_capture(canonical(doc).encode())
    doc["observations"]["orders"] = {"records": [], "traversal_complete": True}
    with pytest.raises(EvidenceError):
        validate_refresh(canonical(doc).encode())


def test_snapshot_exact_values_failed_refresh_preserves_last_good(setup):
    engine, clock, jobs = setup
    api = API()
    service = sync(setup, api)
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(engine) as db:
        first = read_snapshot(db, "shared-isa")
        assert first["total_value"] == api.rows["account_summary"]["records"][0]["totalValue"]
        assert first["quote_age"] == "unknown"
    assert asyncio.run(service.refresh())["status"] == "deferred"
    clock[0] += timedelta(seconds=600)
    api.fail_positions = True
    assert asyncio.run(service.refresh())["status"] == "failed"
    with Session(engine) as db:
        assert read_snapshot(db, "shared-isa") == first
        assert sorted(db.scalars(select(ImportRun.status))) == ["failed", "succeeded"]
    assert count(engine, SourceRecord) == 1


def test_identity_mismatch_stops_without_publication(setup):
    engine, clock, jobs = setup
    api = API()
    api.rows["account_summary"]["records"][0]["id"] = "wrong-account"
    assert asyncio.run(sync(setup, api).refresh())["error"] == "account_identity_mismatch"
    assert count(engine, SourceRecord) == 0
    clock[0] += timedelta(days=1)
    assert jobs.acquire("snapshot") is None


def test_atomic_publication_failure_rolls_back_evidence(setup):
    engine, clock, jobs = setup

    def fail(*args):
        raise RuntimeError("synthetic failure")

    event.listen(SourceRecord, "after_insert", fail)
    try:
        assert asyncio.run(sync(setup, API()).refresh())["status"] == "failed"
    finally:
        event.remove(SourceRecord, "after_insert", fail)
    assert count(engine, SourceRecord) == 0
    with Session(engine) as db:
        assert read_snapshot(db, "shared-isa") is None
    clock[0] += timedelta(seconds=600)
    assert asyncio.run(sync(setup, API()).refresh())["status"] == "succeeded"


def test_concurrent_jobs_and_expired_owner_are_fenced(setup):
    engine, clock, jobs = setup
    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _: jobs.acquire("snapshot"), range(2)))
    assert sum(t is not None for t in tokens) == 1
    old = next(t for t in tokens if t is not None)
    clock[0] += timedelta(seconds=91)
    new = jobs.acquire("snapshot")
    assert new and new != old
    with Session(engine) as db, db.begin(), pytest.raises(BrokerError, match="lease_lost"):
        jobs.owned(db, "snapshot", old)
    jobs.fail("snapshot", old, BrokerError("transport_failure"))
    with Session(engine) as db:
        assert db.get(BrokerSyncJob, ("shared-isa", "snapshot")).lease_token == new


def test_shared_rates_survive_client_replacement_and_provider_reset(setup):
    engine, clock, jobs = setup
    route = PREFIX + "account/summary"
    asyncio.run(jobs.reserve(route))
    other = BrokerJobs(engine, "shared-isa", clock=lambda: clock[0])
    with pytest.raises(Deferred):
        asyncio.run(other.reserve(route))
    deadline = clock[0] + timedelta(hours=1)
    with pytest.raises(Deferred):
        asyncio.run(jobs.observe(route, 429, {"x-ratelimit-reset": str(deadline.timestamp())}))
    clock[0] += timedelta(minutes=20)
    with pytest.raises(Deferred) as caught:
        asyncio.run(other.reserve(route))
    assert caught.value.until == deadline
    clock[0] = deadline
    asyncio.run(other.reserve(route))


def test_rate_reservation_concurrency(setup):
    engine, clock, jobs = setup

    def reserve(_):
        try:
            asyncio.run(jobs.reserve(PREFIX + "positions"))
            return True
        except Deferred:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(4))) == 1


def test_history_staging_completion_duplicates_and_revisions(setup):
    engine, clock, jobs = setup
    api = API()
    rows = api.rows["orders"]["records"]
    api.pages = [(rows[:1], PREFIX + "history/orders?cursor=2&limit=50"), (rows[1:], None)]
    service = sync(setup, api)
    assert asyncio.run(service.history_page("orders"))["status"] == "in_progress"
    assert count(engine, BrokerEventRevision) == 0
    assert count(engine, SourceRecord) == 1
    # A fresh service resumes the durable cursor and atomically accepts all pages.
    assert asyncio.run(sync(setup, api).history_page("orders"))["status"] == "succeeded"
    assert count(engine, BrokerEventRevision) == 3
    with Session(engine) as db:
        split = db.scalar(
            select(BrokerEventRevision).where(
                BrokerEventRevision.external_id == "fill:synthetic-split"
            )
        )
        assert split.quality == "corporate_action_review"
    clock[0] += timedelta(hours=1)
    api.pages = [(rows, None)]
    assert asyncio.run(service.history_page("orders"))["status"] == "succeeded"
    assert count(engine, BrokerEventRevision) == 3
    clock[0] += timedelta(hours=1)
    revised = copy.deepcopy(rows)
    revised[0]["fill"]["quantity"] = "0.5"
    api.pages = [(revised, None)]
    assert asyncio.run(service.history_page("orders"))["status"] == "succeeded"
    assert count(engine, BrokerEventRevision) == 4
    with Session(engine) as db:
        changes = db.scalars(
            select(BrokerEventRevision)
            .where(BrokerEventRevision.external_id == "fill:synthetic-fill")
            .order_by(BrokerEventRevision.revision)
        ).all()
        assert [r.revision for r in changes] == [1, 2]
        assert (
            json.loads(changes[0].payload_json)["fill"]["quantity"]
            != json.loads(changes[1].payload_json)["fill"]["quantity"]
        )


def test_failed_later_page_preserves_checkpoint_and_previous_accepted_events(setup):
    engine, clock, jobs = setup
    api = API()
    rows = api.rows["dividends"]["records"]
    path = PREFIX + "history/dividends?cursor=2"
    api.pages = [(rows, path)]
    service = sync(setup, api)
    assert asyncio.run(service.history_page("dividends"))["status"] == "in_progress"
    assert asyncio.run(service.history_page("dividends"))["status"] == "failed"
    assert count(engine, BrokerEventRevision) == 0
    clock[0] += timedelta(seconds=600)
    api.pages = [([], None)]
    assert asyncio.run(service.history_page("dividends"))["status"] == "succeeded"
    assert count(engine, BrokerEventRevision) == 1


def test_conflicting_identity_in_traversal_rejects_all_revisions(setup):
    engine, clock, jobs = setup
    api = API()
    row = api.rows["transactions"]["records"][0]
    conflicting = dict(row, amount="999")
    api.pages = [([row, conflicting], None)]
    assert (
        asyncio.run(sync(setup, api).history_page("transactions"))["error"]
        == "history_identity_conflict"
    )
    assert count(engine, BrokerEventRevision) == 0
    assert count(engine, SourceRecord) == 0


def test_provider_retry_after_http_date_is_persisted(setup):
    engine, clock, jobs = setup
    route = PREFIX + "positions"
    asyncio.run(jobs.reserve(route))
    asyncio.run(jobs.observe(route, 503, {"retry-after": "Fri, 02 Jan 2026 01:00:00 GMT"}))
    with pytest.raises(Deferred) as caught:
        asyncio.run(jobs.reserve(route))
    assert caught.value.until == NOW + timedelta(hours=1)


def test_cron_next_ten_minute_slot_is_eligible_after_one_second_request(setup):
    engine, clock, jobs = setup
    token = jobs.acquire("snapshot")
    clock[0] += timedelta(seconds=1)
    with Session(engine) as db, db.begin():
        jobs.succeed(jobs.owned(db, "snapshot", token), interval=600)
    clock[0] = NOW + timedelta(seconds=600)
    assert jobs.acquire("snapshot") is not None


def test_admin_resume_fences_active_work_and_restarts_terminal_traversal(setup):
    engine, clock, jobs = setup
    token = jobs.acquire("orders")
    with pytest.raises(ValueError, match="sync_job_active"):
        jobs.resume("orders")
    jobs.fail("orders", token, BrokerError("invalid_response"))
    assert jobs.acquire("orders") is None
    jobs.resume("orders", restart=True)
    assert jobs.acquire("orders") is not None


@pytest.mark.postgres
@pytest.mark.parametrize("fixture_name", ["postgres_engine", "native_engine"])
def test_sync_writer_can_publish_but_cannot_edit_sources_or_other_accounts(request, fixture_name):
    from sqlalchemy.exc import DBAPIError

    engine = request.getfixturevalue(fixture_name)
    with Session(engine) as db, db.begin():
        db.add(Account(id="shared-isa", environment="live", private_reference="synthetic-broker"))
        db.add(Account(id="foreign", environment="demo"))
        db.flush()
        db.add(
            ImportRun(
                id="private-baseline-run",
                account_id="shared-isa",
                kind="excel_migration",
                status="succeeded",
                started_at=NOW,
                finished_at=NOW,
            )
        )
        db.flush()
        db.add(
            SourceRecord(
                id="private-baseline-source",
                run_id="private-baseline-run",
                account_id="shared-isa",
                kind="excel_migration",
                row_number=1,
                schema_version="synthetic",
                payload_json='{"notes":"synthetic private note"}',
                digest="a" * 64,
            )
        )
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    role = "meridian_sync_" + schema

    def restrict(connection):
        connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')

    event.listen(engine, "begin", restrict)
    errors = []

    def capture_error(context):
        errors.append(str(context.original_exception))

    event.listen(engine, "handle_error", capture_error)
    try:
        clock = [NOW]
        jobs = BrokerJobs(engine, "shared-isa", clock=lambda: clock[0])
        service = BrokerSync(engine, "shared-isa", "live", "synthetic-broker", API(), jobs=jobs)
        assert asyncio.run(service.refresh())["status"] == "succeeded", errors
        service.api.pages = [(service.api.rows["orders"]["records"], None)]
        assert asyncio.run(service.history_page("orders"))["status"] == "succeeded"
        from meridian.security.hosted_sync import refresh_metadata

        async def empty_metadata():
            return []

        service.api.instruments = empty_metadata
        service.api.exchanges = empty_metadata
        asyncio.run(refresh_metadata(service))
        with Session(engine) as db:
            assert db.get(BrokerSyncJob, ("shared-isa", "metadata")).last_success_at is not None
        for statement in [
            "UPDATE source_records SET payload_json='{}'",
            "DELETE FROM broker_event_revisions",
            "UPDATE broker_snapshots SET snapshot_json='{}'",
            "SELECT * FROM app_sessions",
            "UPDATE accounts SET private_reference='changed'",
        ]:
            with pytest.raises(DBAPIError), engine.begin() as connection:
                connection.exec_driver_sql(statement)
        with Session(engine) as db:
            assert db.get(Account, "foreign") is None
            assert db.get(ImportRun, "private-baseline-run") is None
            assert db.get(SourceRecord, "private-baseline-source") is None
    finally:
        event.remove(engine, "begin", restrict)
        event.remove(engine, "handle_error", capture_error)
    from meridian.application.refresh_status import refresh_status

    role = "meridian_bff_" + schema
    event.listen(engine, "begin", restrict)
    try:
        with Session(engine) as db:
            assert refresh_status(db, "shared-isa", NOW)["jobs"]["snapshot"]["error"] is None
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.exec_driver_sql("SELECT checkpoint_json FROM broker_sync_jobs")
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.exec_driver_sql("SELECT * FROM broker_event_revisions")
    finally:
        event.remove(engine, "begin", restrict)


def test_cron_jitter_does_not_skip_the_next_ten_minute_slot(setup):
    engine, clock, jobs = setup
    clock[0] = NOW + timedelta(seconds=1.5)
    token = jobs.acquire("snapshot")
    clock[0] += timedelta(seconds=2)
    with Session(engine) as db, db.begin():
        jobs.succeed(jobs.owned(db, "snapshot", token), interval=600)
    clock[0] = NOW + timedelta(seconds=600.2)
    assert jobs.acquire("snapshot") is not None


def test_hosted_history_stops_when_current_credentials_return_another_account(setup, monkeypatch):
    from meridian.security import hosted_sync

    engine, clock, jobs = setup
    api = API()
    api.rows["account_summary"]["records"][0]["id"] = "another-account"
    calls = []

    class HostedAPI(API):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def history_page(self, *args):
            calls.append(True)
            return [], None

    hosted = HostedAPI()
    hosted.rows = api.rows
    monkeypatch.setattr(hosted_sync, "create_binding_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(hosted_sync, "Trading212Client", lambda **kwargs: hosted)
    monkeypatch.setattr(hosted_sync, "session_state", lambda *args: "unknown")
    result = asyncio.run(
        hosted_sync.run_sync(
            None, api_key="synthetic", api_secret="synthetic", environment="live", scheduled=True
        )
    )
    assert result["status"] == "failed"
    assert calls == []
    assert count(engine, BrokerEventRevision) == 0


def test_manual_transport_failure_returns_durable_retry_deadline(setup, monkeypatch):
    from meridian.security import hosted_sync

    engine, clock, jobs = setup
    api = API()
    api.fail_positions = True
    monkeypatch.setattr(hosted_sync, "create_binding_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(hosted_sync, "Trading212Client", lambda **kwargs: api)
    result = asyncio.run(
        hosted_sync.run_sync(
            None, api_key="synthetic", api_secret="synthetic", environment="live", scheduled=False
        )
    )
    assert result["status"] == "failed"
    with Session(engine) as db:
        job = db.get(BrokerSyncJob, ("shared-isa", "snapshot"))
        assert result["retry_at"] == job.next_attempt_at.isoformat()


def test_history_replay_batches_existing_revision_reads(setup):
    engine, clock, jobs = setup
    api = API()
    template = api.rows["transactions"]["records"][0]
    rows = [dict(template, reference=f"synthetic-{i}") for i in range(1101)]
    api.pages = [(rows, None)]
    service = sync(setup, api)
    assert asyncio.run(service.history_page("transactions"))["status"] == "succeeded"
    clock[0] += timedelta(hours=1)
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    api.pages = [(rows, None)]
    event.listen(engine, "before_cursor_execute", record)
    try:
        assert asyncio.run(service.history_page("transactions"))["status"] == "succeeded"
    finally:
        event.remove(engine, "before_cursor_execute", record)
    revision_reads = [
        sql
        for sql in statements
        if sql.lstrip().upper().startswith("SELECT") and "broker_event_revisions" in sql
    ]
    assert len(revision_reads) == 3  # 500, 500 and 101, rather than 1,101 lookups.
    assert count(engine, BrokerEventRevision) == len(rows)


def test_successful_response_without_rate_deadline_does_not_query_database(setup):
    engine, clock, jobs = setup
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        asyncio.run(jobs.observe(PREFIX + "positions", 200, {}))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements == []


def test_ten_minute_cooldown_and_twenty_minute_staleness(setup):
    from meridian.application.refresh_status import refresh_status

    engine, clock, jobs = setup
    assert asyncio.run(sync(setup, API()).refresh())["status"] == "succeeded"
    clock[0] += timedelta(minutes=9)
    assert jobs.acquire("snapshot") is None
    with Session(engine) as db:
        status = refresh_status(db, "shared-isa", clock[0])
        assert status["target_interval_seconds"] == 600
        assert not status["jobs"]["snapshot"]["stale"]
        assert refresh_status(db, "shared-isa", NOW + timedelta(minutes=21))["jobs"]["snapshot"][
            "stale"
        ]
    clock[0] += timedelta(minutes=1)
    assert jobs.acquire("snapshot") is not None


@pytest.mark.skipif(not os.environ.get("AXIS_NODE_TEST_BINARY"), reason="generated WASM required")
def test_exposures_publish_atomically_and_fail_open(setup):
    engine, clock, jobs = setup
    api = API()
    first = api.rows["positions"]["records"][0]
    first["instrument"].pop("currency", None)
    first["instrument"].pop("isin", None)
    first["walletImpact"] = {"currency": "GBP", "currentValue": "12.000000000000000000001"}
    ticker = first["instrument"]["ticker"]
    missing = "SYNTH_MISSING"
    api.rows["positions"]["records"].append({"instrument": {"ticker": missing}, "quantity": "1"})
    service = sync(setup, api)
    with Session(engine) as db, db.begin():
        run = service.new_run(db, "trading212_metadata")
        run.status, run.finished_at = "succeeded", clock[0]
        db.add(
            source_record(
                "shared-isa",
                run.id,
                1,
                "trading212_metadata",
                {
                    "requested_tickers": [ticker, missing],
                    "retrieved_at": clock[0].isoformat(),
                    "instruments": [
                        {"ticker": ticker, "currencyCode": "USD", "isin": "SYNTHETIC001"}
                    ],
                },
            )
        )

    active = []
    event.listen(engine, "begin", lambda connection: active.append(connection))
    event.listen(engine, "rollback", lambda connection: active.remove(connection))
    event.listen(engine, "commit", lambda connection: active.remove(connection))
    wasm = (
        Path(__file__).resolve().parents[2] / "prototype/worker-feasibility/src/reconciliation_wasm"
    )

    async def calculate(encoded):
        assert not active
        request = json.loads(encoded)
        assert request["positions"][0]["quote_currency"] == "USD"
        assert request["positions"][0]["isin"] == "SYNTHETIC001"
        assert "scope" not in request and "history" not in request
        result = subprocess.run(
            [
                os.environ["AXIS_NODE_TEST_BINARY"],
                "--input-type=module",
                "-e",
                """
                import fs from 'node:fs';
                import {initSync, portfolio_exposures_json} from './axis_reconciliation.mjs';
                const bytes=fs.readFileSync("axis_reconciliation_bg.wasm");
                initSync({module:new WebAssembly.Module(bytes)});
                process.stdout.write(portfolio_exposures_json(fs.readFileSync(0,'utf8')));
            """,
            ],
            input=encoded,
            text=True,
            capture_output=True,
            timeout=5,
            cwd=wasm,
            check=True,
        )
        return result.stdout

    service.exposure_calculator = calculate
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(engine) as db:
        initial = read_snapshot(db, "shared-isa")
        report = initial["exposures"]
        assert report["snapshot_id"] == db.scalar(select(BrokerSnapshot.id))
        assert report["positions_as_of"] == initial["positions_retrieval"]["retrieval_completed_at"]
        assert report["holdings"][0]["value"] == "12.000000000000000000001"
        assert report["missing_values"] == 1
        assert report["sectors"]["buckets"][0]["label"] is None
        assert report["sectors"]["classified"]["value"] == "0"
        assert report["quote_currencies"][0]["quote_currency"] == "USD"
        assert report["quote_currencies"][1]["quote_currency"] is None
        assert initial["positions"][0]["quote_currency_source"] == "instrument_metadata"

    async def bad_result(encoded):
        assert not active
        return '{"method":"broker_exposures_v1","snapshot_id":"foreign"}'

    clock[0] += timedelta(minutes=10)
    service.exposure_calculator = bad_result
    assert asyncio.run(service.refresh())["status"] == "succeeded"
    with Session(engine) as db:
        snapshot = read_snapshot(db, "shared-isa")
        assert snapshot["exposures"]["availability"] == "failed"
        for key in ("positions", "total_value", "cash_components"):
            assert initial[key] == snapshot[key]

    clock[0] += timedelta(minutes=10)
    api.fail_positions = True
    assert asyncio.run(service.refresh())["status"] == "failed"
    with Session(engine) as db:
        assert read_snapshot(db, "shared-isa") == snapshot
