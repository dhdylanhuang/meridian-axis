"""Synthetic broker-led discovery with the existing leases and publication path."""

import asyncio
import copy
import json
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_broker_ingestion import NOW, capture_document
from test_broker_ingestion import engine as engine
from test_broker_sync import API

from meridian.adapters.broker_evidence import canonical, validate_capture
from meridian.adapters.trading212 import BrokerError
from meridian.application.broker_jobs import BrokerJobs
from meridian.application.broker_metadata import latest_metadata, refresh_metadata
from meridian.application.broker_snapshot import broker_snapshot
from meridian.application.broker_sync import BrokerSync
from meridian.application.snapshot_access import read_snapshot
from meridian.persistence.models import Account, BrokerSnapshot, BrokerSyncJob


class MetadataAPI(API):
    def __init__(self):
        super().__init__()
        self.metadata_calls = 0
        self.metadata_error = None
        self.catalogue = [
            {
                "ticker": "SYNTH",
                "name": "Synthetic fund",
                "currencyCode": "USD",
                "isin": "SYNTHETIC",
                "type": "ETF",
                "workingScheduleId": 1,
            }
        ]

    async def instruments(self):
        self.metadata_calls += 1
        if self.metadata_error:
            raise self.metadata_error
        return [SimpleNamespace(raw_payload=row) for row in self.catalogue]

    async def exchanges(self):
        return [
            SimpleNamespace(
                raw_payload={
                    "id": 1,
                    "name": "Synthetic exchange",
                    "workingSchedules": [{"id": 1, "timeEvents": []}],
                }
            )
        ]


@pytest.fixture
def driver(engine):
    with Session(engine) as db, db.begin():
        db.get(Account, "shared-isa").private_reference = "synthetic-broker"
    clock = [NOW]
    jobs = BrokerJobs(engine, "shared-isa", clock=lambda: clock[0], random_value=lambda: 1)
    api = MetadataAPI()
    service = BrokerSync(engine, "shared-isa", "live", "synthetic-broker", api, jobs=jobs)
    return service, api, clock


def saved(service):
    with Session(service.engine) as db:
        return read_snapshot(db, "shared-isa")


def refresh(service):
    assert asyncio.run(service.refresh())["status"] == "succeeded"


def test_new_holding_enriches_after_existing_metadata_job_without_changing_money(driver):
    service, api, clock = driver
    refresh(service)
    initial = saved(service)
    assert initial["holding_changes"]["basis"] == "initial_observation"
    assert initial["positions"][0]["metadata"]["state"] == "pending"
    asyncio.run(refresh_metadata(service))
    assert api.metadata_calls == 1
    clock[0] += timedelta(minutes=10)
    refresh(service)
    enriched = saved(service)
    position = enriched["positions"][0]
    assert position["name"] == "Synthetic fund"
    assert position["isin"] == "SYNTHETIC"
    assert position["instrument_type"] == "ETF"
    assert position["metadata"]["state"] == "available"
    for key in (
        "quantity",
        "current_price",
        "current_value",
        "total_cost",
        "unrealized_profit_loss",
    ):
        assert position[key] == initial["positions"][0][key]
    assert enriched["total_value"] == initial["total_value"]
    assert enriched["quote_timestamp"] is None
    # Introduce a position while the normal daily metadata cooldown is active.
    added = copy.deepcopy(api.rows["positions"]["records"][0])
    added["instrument"] = {"ticker": "NEW", "currency": "GBP"}
    api.rows["positions"]["records"].append(added)
    api.catalogue.append(
        {"ticker": "NEW", "currencyCode": "GBP", "name": "New fund", "type": "ETF"}
    )
    clock[0] += timedelta(minutes=10)
    refresh(service)
    assert saved(service)["holding_changes"]["added_tickers"] == ["NEW"]
    asyncio.run(refresh_metadata(service))
    assert api.metadata_calls == 2
    asyncio.run(refresh_metadata(service))
    assert api.metadata_calls == 2  # no repeated lookup for the same requested scope
    clock[0] += timedelta(minutes=10)
    refresh(service)
    assert (
        next(r for r in saved(service)["positions"] if r["ticker"] == "NEW")["name"] == "New fund"
    )
    assert saved(service)["holding_changes"]["added_tickers"] == []
    api.rows["positions"]["records"] = [added]
    clock[0] += timedelta(minutes=10)
    refresh(service)
    assert saved(service)["holding_changes"]["closed_tickers"] == ["SYNTH"]
    asyncio.run(refresh_metadata(service))
    assert api.metadata_calls == 2  # closure alone does not shorten the daily cooldown


def test_missing_catalogue_entry_is_explicit_and_does_not_loop(driver):
    service, api, clock = driver
    api.catalogue = []
    refresh(service)
    asyncio.run(refresh_metadata(service))
    clock[0] += timedelta(minutes=10)
    refresh(service)
    assert saved(service)["positions"][0]["metadata"]["state"] == "missing"
    asyncio.run(refresh_metadata(service))
    assert api.metadata_calls == 1
    with Session(service.engine) as db:
        assert json.loads(latest_metadata(db, "shared-isa").payload_json)["missing_tickers"] == [
            "SYNTH"
        ]


@pytest.mark.parametrize(
    "error", [BrokerError("transport_failure"), BrokerError("invalid_response")]
)
def test_metadata_failure_preserves_snapshot_and_retry_pause_for_new_scope(driver, error):
    service, api, clock = driver
    refresh(service)
    asyncio.run(refresh_metadata(service))
    clock[0] += timedelta(days=1)
    api.metadata_error = error
    asyncio.run(refresh_metadata(service))
    with Session(service.engine) as db:
        job = db.get(BrokerSyncJob, ("shared-isa", "metadata"))
        retry = job.next_attempt_at
        assert job.failures == 1
    assert service.jobs.acquire("metadata", metadata_tickers=["ANOTHER_NEW"]) is None
    refresh(service)
    assert (
        saved(service)["total_value"]
        == capture_document()["observations"]["account_summary"]["records"][0]["totalValue"]
    )
    with Session(service.engine) as db:
        assert db.get(BrokerSyncJob, ("shared-isa", "metadata")).next_attempt_at == retry


def test_new_scope_cannot_steal_active_metadata_lease(driver):
    service, api, clock = driver
    refresh(service)
    asyncio.run(refresh_metadata(service))
    token = service.jobs.acquire("metadata", metadata_tickers=["NEW"])
    assert token is not None
    assert service.jobs.acquire("metadata", metadata_tickers=["OTHER"]) is None
    with Session(service.engine) as db:
        assert service.jobs.owned(db, "metadata", token).lease_token == token


@pytest.mark.parametrize("kind", ["manual", "scheduled"])
def test_hosted_success_dispatches_same_metadata_job(driver, monkeypatch, kind):
    from meridian.security import hosted_sync

    service, api, clock = driver
    monkeypatch.setattr(hosted_sync, "create_binding_engine", lambda *a, **k: service.engine)
    monkeypatch.setattr(hosted_sync, "Trading212Client", lambda **k: api)
    monkeypatch.setattr(hosted_sync, "BrokerJobs", lambda *a, **k: service.jobs)
    monkeypatch.setattr(hosted_sync, "session_state", lambda *a: "unknown")
    api.pages = [([], None)]
    result = asyncio.run(
        hosted_sync.run_sync(
            None,
            api_key="synthetic",
            api_secret="synthetic",
            environment="live",
            scheduled=kind == "scheduled",
        )
    )
    assert result["status"] == "succeeded"
    assert api.metadata_calls == 1
    assert saved(service)["positions"][0]["metadata"]["state"] == "pending"


def test_projection_respects_position_authority_and_exposes_stale_conflicting_metadata():
    document = capture_document()
    instrument = document["observations"]["positions"]["records"][0]["instrument"]
    instrument["name"] = "Position name"
    metadata = {
        "source_id": "safe-source",
        "payload": {
            "requested_tickers": ["SYNTH"],
            "retrieved_at": (NOW - timedelta(days=2)).isoformat(),
            "instruments": [
                {"ticker": "SYNTH", "currencyCode": "USD", "name": "Metadata name", "isin": "SYN"}
            ],
        },
    }
    evidence = validate_capture(canonical(document).encode())
    result = broker_snapshot(evidence, metadata=metadata)
    assert result["positions"][0]["name"] == "Position name"
    assert result["positions"][0]["metadata"]["state"] == "stale"
    metadata["payload"]["instruments"][0]["currencyCode"] = "EUR"
    result = broker_snapshot(evidence, metadata=metadata)
    assert result["positions"][0]["instrument_currency"] == "USD"
    assert result["positions"][0]["metadata"]["state"] == "conflict"
    assert result["positions"][0]["isin"] is None


def test_publication_retains_old_snapshots_and_no_raw_catalogue_in_projection(driver):
    service, api, clock = driver
    api.catalogue.append(
        {"ticker": "UNHELD", "name": "Never publish", "currencyCode": "GBP", "type": "ETF"}
    )
    refresh(service)
    before = saved(service)
    asyncio.run(refresh_metadata(service))
    clock[0] += timedelta(minutes=10)
    refresh(service)
    with Session(service.engine) as db:
        snapshots = db.scalars(select(BrokerSnapshot).order_by(BrokerSnapshot.observed_at)).all()
        assert len(snapshots) == 2
        assert json.loads(snapshots[0].snapshot_json) == before
        assert "UNHELD" not in snapshots[-1].snapshot_json
        assert "Never publish" not in latest_metadata(db, "shared-isa").payload_json
