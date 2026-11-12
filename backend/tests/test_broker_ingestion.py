"""Entirely synthetic capture validation and immutable evidence acceptance."""

import copy
import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_supabase_migration import native_engine as native_engine

from meridian.adapters.broker_evidence import EvidenceError, canonical, validate_capture
from meridian.application.broker_ingestion import ingest_capture
from meridian.application.broker_snapshot import broker_snapshot
from meridian.application.imports import ImportValidationError
from meridian.persistence.database import create_db_engine, upgrade_database
from meridian.persistence.models import Account, AuditRecord, ImportRun, SourceRecord

NOW = datetime(2026, 1, 2, tzinfo=UTC)


def capture_document():
    rows = {
        "account_summary": [
            {
                "id": "synthetic-broker",
                "currency": "GBP",
                "totalValue": "999.12345678901234567890123456789",
                "investments": {"currentValue": "123.45", "totalCost": "100"},
                "cash": {"availableToTrade": "70", "inPies": "20", "reservedForOrders": "5"},
            }
        ],
        "positions": [
            {
                "instrument": {"ticker": "SYNTH", "currency": "USD"},
                "quantity": "1.125000000000000000000001",
                "currentPrice": "19.00",
                "walletImpact": {"currency": "GBP", "currentValue": "12.34", "totalCost": "11"},
            }
        ],
        "orders": [
            {
                "order": {
                    "id": "synthetic-order",
                    "side": "BUY",
                    "instrument": {"ticker": "SYNTH"},
                },
                "fill": {
                    "id": "synthetic-fill",
                    "type": "TRADE",
                    "quantity": "0.125000000000000000000001",
                    "price": "12.40",
                    "filledAt": "2026-01-01T00:00:00Z",
                },
            },
            {
                "order": {
                    "id": "synthetic-split-order",
                    "side": "BUY",
                    "instrument": {"ticker": "SYNTH"},
                },
                "fill": {
                    "id": "synthetic-split",
                    "type": "STOCK_SPLIT",
                    "quantity": "1",
                    "filledAt": "2026-01-01T01:00:00Z",
                },
            },
            {
                "order": {
                    "id": "synthetic-cancelled",
                    "side": "BUY",
                    "instrument": {"ticker": "SYNTH"},
                },
                "fill": None,
            },
        ],
        "dividends": [
            {
                "reference": "shared-ref",
                "paidOn": "2026-01-01T01:00:00+00:00",
                "amount": "0.0123456789012345678901",
                "currency": "GBP",
            }
        ],
        "transactions": [
            {
                "reference": "shared-ref",
                "dateTime": "2026-01-01T01:00:00+00:00",
                "amount": "-0.1",
                "currency": "GBP",
                "type": "WITHDRAW",
            }
        ],
        "instruments": [],
        "exchanges": [],
    }
    return {
        "version": 1,
        "environment": "live",
        "source": "trading212_api_v0",
        "numeric_encoding": "decimal_strings",
        "historical_lifetime_coverage": "unverified",
        "ledger_reconciled": False,
        "observations": {
            family: {
                "records": records,
                "traversal_complete": True,
                "retrieval_started_at": NOW.isoformat(),
                "retrieval_completed_at": NOW.isoformat(),
            }
            for family, records in rows.items()
        },
    }


def encoded(doc=None):
    return canonical(doc if doc is not None else capture_document()).encode()


@pytest.fixture
def engine(tmp_path):
    path = tmp_path / "synthetic.sqlite3"
    upgrade_database(path)
    engine = create_db_engine(path)
    with Session(engine) as session, session.begin():
        session.add(Account(id="shared-isa", environment="live"))
    yield engine
    engine.dispose()


def ingest(engine, **overrides):
    return ingest_capture(
        engine,
        **(
            {
                "account_id": "shared-isa",
                "environment": "live",
                "expected_broker_reference": "synthetic-broker",
                "bind_unset_reference": True,
                "content": encoded(),
                "clock": lambda: NOW,
            }
            | overrides
        ),
    )


def test_broker_totals_are_authoritative_even_when_position_sum_differs():
    snapshot = broker_snapshot(validate_capture(encoded()))
    assert snapshot["total_value"] == "999.12345678901234567890123456789"
    assert snapshot["investments"]["currentValue"] == "123.45"
    assert snapshot["positions"][0]["current_value"] == "12.34"
    assert snapshot["cash_components"] == {
        "availableToTrade": "70",
        "inPies": "20",
        "reservedForOrders": "5",
    }
    assert snapshot["historical_returns"] is None
    assert snapshot["quote_timestamp"] is None
    assert "synthetic-broker" not in json.dumps(snapshot)


def test_acceptance_is_evidence_only_exact_atomic_and_audited(engine):
    report = ingest(engine)
    assert report.status == "succeeded" and report.counts["economic_events_added"] == 0
    with Session(engine) as session:
        assert session.get(Account, "shared-isa").private_reference == "synthetic-broker"
        sources = session.scalars(select(SourceRecord)).all()
        assert len(sources) == 10
        assert all(
            hashlib.sha256(row.payload_json.encode()).hexdigest() == row.digest for row in sources
        )
        assert any("0.125000000000000000000001" in row.payload_json for row in sources)
        assert any("STOCK_SPLIT" in row.payload_json for row in sources)
        assert len(session.scalars(select(AuditRecord)).all()) == 1
        assert "synthetic-broker" not in session.scalars(select(AuditRecord)).one().details_json


def test_canonical_duplicate_is_rejected_without_new_sources_or_audit(engine):
    assert ingest(engine).status == "succeeded"
    before = None
    with Session(engine) as session:
        before = len(session.scalars(select(SourceRecord)).all())
    report = ingest(engine, content=json.dumps(capture_document(), indent=3).encode())
    assert report.status == "duplicate"
    with Session(engine) as session:
        assert len(session.scalars(select(SourceRecord)).all()) == before
        assert len(session.scalars(select(AuditRecord)).all()) == 1
        assert len(session.scalars(select(ImportRun)).all()) == 2


def test_late_storage_failure_rolls_back_reference_evidence_audit_and_logs_failure(engine):
    def fail(_mapper, _connection, _target):
        raise RuntimeError("synthetic-private-payload")

    event.listen(AuditRecord, "before_insert", fail)
    try:
        report = ingest(engine)
    finally:
        event.remove(AuditRecord, "before_insert", fail)
    assert report.status == "failed" and report.safe_error == "broker_evidence_storage_failed"
    with Session(engine) as session:
        assert session.get(Account, "shared-isa").private_reference is None
        assert not session.scalars(select(SourceRecord)).all()
        assert not session.scalars(select(AuditRecord)).all()
        assert session.get(ImportRun, report.run_id).status == "failed"


@pytest.mark.parametrize(
    "change",
    [
        "environment",
        "reference",
        "incomplete",
        "timestamp",
        "duplicate_fill",
        "duplicate_cash",
        "missing_family",
        "float",
        "nonfinite",
        "sensitive",
    ],
)
def test_invalid_capture_durably_fails_without_source_residue(engine, change):
    doc = capture_document()
    if change == "environment":
        doc["environment"] = "demo"
    elif change == "reference":
        doc["observations"]["account_summary"]["records"][0]["id"] = "other-account"
    elif change == "incomplete":
        doc["observations"]["transactions"]["traversal_complete"] = False
    elif change == "timestamp":
        doc["observations"]["orders"]["retrieval_started_at"] = "2026-01-01"
    elif change == "duplicate_fill":
        doc["observations"]["orders"]["records"].append(
            copy.deepcopy(doc["observations"]["orders"]["records"][0])
        )
    elif change == "duplicate_cash":
        doc["observations"]["transactions"]["records"] *= 2
    elif change == "missing_family":
        del doc["observations"]["exchanges"]
    elif change == "float":
        doc["observations"]["positions"]["records"][0]["quantity"] = 0.125
    elif change == "nonfinite":
        doc["observations"]["positions"]["records"][0]["quantity"] = "NaN"
    elif change == "sensitive":
        doc["authorization"] = "synthetic-private-secret"
    report = ingest(engine, content=encoded(doc))
    assert report.status == "failed"
    assert "synthetic-private" not in str(report)
    with Session(engine) as session:
        assert not session.scalars(select(SourceRecord)).all()
        assert session.get(Account, "shared-isa").private_reference is None


def test_explicit_binding_and_scope_required_before_logging(engine):
    with pytest.raises(ImportValidationError, match="binding_required"):
        ingest(engine, bind_unset_reference=False)
    with pytest.raises(ImportValidationError, match="scope_mismatch"):
        ingest(engine, environment="demo")
    with Session(engine) as session:
        assert not session.scalars(select(ImportRun)).all()


def test_existing_different_broker_binding_is_never_overwritten(engine):
    with Session(engine) as session, session.begin():
        session.get(Account, "shared-isa").private_reference = "another-broker-account"
    with pytest.raises(ImportValidationError, match="binding_required"):
        ingest(engine)


def test_duplicate_json_keys_are_rejected_without_echo():
    with pytest.raises(EvidenceError, match="duplicate_json_key"):
        validate_capture(b'{"private":"one","private":"two"}')


# Actual database qualification uses disposable loopback schemas only, through
# both reviewed migration paths. No fixture accepts a hosted database URL.


@pytest.fixture(params=["postgres_engine", "native_engine"])
def pg_broker_engine(request):
    engine = request.getfixturevalue(request.param)
    with Session(engine) as session, session.begin():
        session.add(Account(id="shared-isa", environment="live"))
    return engine


@pytest.mark.postgres
def test_postgres_capture_acceptance_and_replay(pg_broker_engine):
    test_acceptance_is_evidence_only_exact_atomic_and_audited(pg_broker_engine)
    report = ingest(pg_broker_engine, content=json.dumps(capture_document(), indent=2).encode())
    assert report.status == "duplicate"


@pytest.mark.postgres
def test_postgres_capture_failure_and_retry(pg_broker_engine):
    test_late_storage_failure_rolls_back_reference_evidence_audit_and_logs_failure(pg_broker_engine)
    assert ingest(pg_broker_engine).status == "succeeded"


def test_missing_optional_broker_figure_stays_unavailable():
    doc = capture_document()
    del doc["observations"]["positions"]["records"][0]["walletImpact"]
    result = broker_snapshot(validate_capture(encoded(doc)))
    assert result["positions"][0]["current_value"] is None
    assert (
        result["total_value"] == doc["observations"]["account_summary"]["records"][0]["totalValue"]
    )


def test_unknown_corporate_action_is_preserved_without_economic_posting(engine):
    doc = capture_document()
    doc["observations"]["orders"]["records"][1]["fill"]["type"] = "FUTURE_PROVIDER_ACTION"
    report = ingest(engine, content=encoded(doc))
    assert report.status == "succeeded" and report.counts["economic_events_added"] == 0
    with Session(engine) as session:
        assert any(
            "FUTURE_PROVIDER_ACTION" in row.payload_json
            for row in session.scalars(select(SourceRecord))
        )
