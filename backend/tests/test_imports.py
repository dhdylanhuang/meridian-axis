"""Atomic snapshot evidence services with entirely invented CSV inputs."""

import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from meridian.adapters.holdings_csv import REQUIRED_HEADERS, HoldingsCSVError
from meridian.application import imports
from meridian.application.imports import ImportValidationError, import_holdings, preview_holdings
from meridian.persistence.database import create_db_engine, upgrade_database
from meridian.persistence.models import Account, AuditRecord, ImportRun, SourceRecord

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)


def fixture_bytes():
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(REQUIRED_HEADERS)
    writer.writerow(
        ["SYN", "Invented Holding", "100.123", "102.123", "2", "1.5", "N/A", "N/A", "N/A"]
    )
    writer.writerow(["Total", "Invented Group", "100.123", "102.123", "2", "-", "5", "1", "2"])
    return stream.getvalue().encode("utf-8-sig")


@pytest.fixture
def engine(tmp_path):
    path = tmp_path / "synthetic.db"
    upgrade_database(path)
    engine = create_db_engine(path)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                Account(id="demo-isa", environment="demo"),
                Account(id="live-isa", environment="live"),
            ]
        )
    yield engine
    engine.dispose()


def run_import(engine, **overrides):
    return import_holdings(
        engine,
        **(
            {
                "account_id": "demo-isa",
                "content": fixture_bytes(),
                "currency": "GBP",
                "observed_at": NOW,
                "clock": lambda: NOW,
            }
            | overrides
        ),
    )


def test_preview_validates_without_creating_operation_or_evidence(engine):
    result = preview_holdings(fixture_bytes(), currency="GBP", observed_at=NOW)
    assert result.group_name == "Invented Group"
    with Session(engine) as session:
        assert session.scalars(select(ImportRun)).all() == []
        assert session.scalars(select(SourceRecord)).all() == []


def test_oversized_prefix_never_claims_full_file_digest(engine):
    report = run_import(engine, max_bytes=10)
    assert report.status == "failed"
    assert report.safe_error == "file_too_large"
    with Session(engine) as session:
        assert session.get(ImportRun, report.run_id).content_hash is None
        assert session.scalars(select(SourceRecord)).all() == []


def test_success_keeps_raw_and_normalized_snapshot_evidence_not_economic_events(engine):
    report = run_import(engine)
    assert report.status == "succeeded"
    assert report.safe_error is None
    assert report.counts == {
        "rows_read": 2,
        "holding_rows": 1,
        "control_rows": 1,
        "source_records_added": 2,
        "economic_events_added": 0,
        "duplicate_files": 0,
        "rejected_files": 0,
    }
    with Session(engine) as session:
        run = session.get(ImportRun, report.run_id)
        assert run.content_hash == hashlib.sha256(fixture_bytes()).hexdigest()
        assert run.status == "succeeded"
        assert run.started_at == run.finished_at == NOW
        assert json.loads(run.counts_json) == report.counts
        sources = session.scalars(select(SourceRecord).order_by(SourceRecord.row_number)).all()
        assert [source.kind for source in sources] == [
            "holdings_snapshot_row",
            "holdings_snapshot_control",
        ]
        holding, control = [json.loads(source.payload_json) for source in sources]
        assert holding["normalized"]["owned_quantity"] == "1.5"
        assert holding["normalized"]["invested_value"] == "100.123"
        assert holding["normalized"]["dividends_gained"] is None
        assert dict(holding["raw_fields"])["Slice"] == "SYN"
        assert holding["raw_text"].startswith("SYN,Invented Holding,")
        assert holding["context"]["group_label"] == "Invented Group"
        assert holding["context"]["currency"] == "GBP"
        assert holding["context"]["observation_time_basis"] == "caller_supplied"
        assert control["normalized"]["dividends_gained"] == "5"
        assert control["evidence_only"] is True
        for source in sources:
            assert source.digest == hashlib.sha256(source.payload_json.encode("utf-8")).hexdigest()
        audit = session.scalars(select(AuditRecord)).one()
        assert audit.run_id == report.run_id
        assert audit.actor == "local-admin"
        assert json.loads(audit.details_json)["evidence_only"] is True


def test_replay_logs_duplicate_without_adding_source_or_audit_rows(engine):
    first = run_import(engine)
    repeated = run_import(engine)
    assert repeated.run_id != first.run_id
    assert repeated.status == "duplicate"
    assert repeated.safe_error == "duplicate_file"
    assert repeated.counts["source_records_added"] == 0
    with Session(engine) as session:
        assert len(session.scalars(select(ImportRun)).all()) == 2
        assert len(session.scalars(select(SourceRecord)).all()) == 2
        assert len(session.scalars(select(AuditRecord)).all()) == 1


def test_same_file_is_independently_scoped_to_another_account(engine):
    assert run_import(engine).status == "succeeded"
    assert run_import(engine, account_id="live-isa").status == "succeeded"
    with Session(engine) as session:
        assert len(session.scalars(select(SourceRecord)).all()) == 4


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"account_id": "missing"}, "account_not_found"),
        ({"currency": "USD"}, "account_currency_mismatch"),
        ({"actor": ""}, "invalid_actor"),
    ],
)
def test_invalid_administrative_context_creates_no_run(engine, overrides, code):
    with pytest.raises(ImportValidationError, match=code):
        run_import(engine, **overrides)
    with Session(engine) as session:
        assert session.scalars(select(ImportRun)).all() == []


def test_invalid_file_has_durable_failed_attempt_without_partial_evidence(engine):
    report = run_import(engine, content=b"bad,headers\r\nsecret,private-value\r\n")
    assert report.status == "failed"
    assert report.safe_error == "missing_headers"
    assert report.counts["rows_read"] is None
    with Session(engine) as session:
        run = session.get(ImportRun, report.run_id)
        assert run.status == "failed"
        assert run.error_code == "missing_headers"
        assert "private-value" not in run.counts_json
        assert session.scalars(select(SourceRecord)).all() == []
        assert session.scalars(select(AuditRecord)).all() == []


def test_failure_during_write_rolls_back_evidence_audit_and_success_then_logs_failure(engine):
    def fail_after_insert(_mapper, _connection, _target):
        raise RuntimeError("pretend-secret-and-private-financial-payload")

    event.listen(SourceRecord, "after_insert", fail_after_insert)
    try:
        report = run_import(engine)
    finally:
        event.remove(SourceRecord, "after_insert", fail_after_insert)
    assert report.status == "failed"
    assert report.safe_error == "import_storage_failed"
    assert report.counts["source_records_added"] == 0
    with Session(engine) as session:
        run = session.get(ImportRun, report.run_id)
        assert run.status == "failed"
        assert run.error_code == "import_storage_failed"
        assert session.scalars(select(SourceRecord)).all() == []
        assert session.scalars(select(AuditRecord)).all() == []
    # Failed attempts do not occupy the successful-hash uniqueness constraint.
    assert run_import(engine).status == "succeeded"


def test_parse_runs_after_running_operation_is_committed_and_outside_write_transaction(
    engine, monkeypatch
):
    original = imports.preview_holdings

    def checked_preview(*args, **kwargs):
        with Session(engine) as session, session.begin():
            run = session.scalars(select(ImportRun)).one()
            assert run.status == "running"
            # A separate writer can commit while parsing; no import write lock.
            session.add(Account(id="parse-check", environment="demo"))
        return original(*args, **kwargs)

    monkeypatch.setattr(imports, "preview_holdings", checked_preview)
    assert run_import(engine).status == "succeeded"


def test_preview_failure_never_creates_an_operation(engine):
    with pytest.raises(HoldingsCSVError):
        preview_holdings(b"invalid", currency="GBP", observed_at=NOW)
    with Session(engine) as session:
        assert session.scalars(select(ImportRun)).all() == []


def test_accepted_hash_race_is_logged_as_duplicate_without_orphan_evidence(engine, monkeypatch):
    original = imports.preview_holdings
    nested = False

    def racing_preview(*args, **kwargs):
        nonlocal nested
        if not nested:
            nested = True
            assert run_import(engine).status == "succeeded"
        return original(*args, **kwargs)

    monkeypatch.setattr(imports, "preview_holdings", racing_preview)
    report = run_import(engine)
    assert report.status == "duplicate"
    assert report.counts["source_records_added"] == 0
    with Session(engine) as session:
        assert len(session.scalars(select(SourceRecord)).all()) == 2
        assert len(session.scalars(select(AuditRecord)).all()) == 1
        statuses = session.scalars(select(ImportRun.status)).all()
        assert sorted(statuses) == ["duplicate", "succeeded"]


def test_size_failure_and_bad_observation_time_are_logged_with_safe_categories(engine):
    oversized = run_import(engine, max_bytes=1)
    assert oversized.safe_error == "file_too_large"
    unknown_time = run_import(engine, observed_at=datetime(2026, 1, 2))
    assert unknown_time.safe_error == "observation_time_required"


def test_nonduplicate_integrity_failure_is_not_misreported_as_a_duplicate(engine, monkeypatch):
    original = imports._source_record

    def invalid_source(*args, **kwargs):
        source = original(*args, **kwargs)
        source.account_id = "missing-account"
        return source

    monkeypatch.setattr(imports, "_source_record", invalid_source)
    report = run_import(engine)
    assert report.status == "failed"
    assert report.safe_error == "import_storage_failed"
    assert report.counts["duplicate_files"] == 0
    with Session(engine) as session:
        assert session.get(ImportRun, report.run_id).status == "failed"
        assert session.scalars(select(SourceRecord)).all() == []
        assert session.scalars(select(AuditRecord)).all() == []


def test_unexpected_parser_failure_is_logged_without_exposing_exception_text(engine, monkeypatch):
    def broken_parser(*_args, **_kwargs):
        raise RuntimeError("private-payload-not-for-logs")

    monkeypatch.setattr(imports, "preview_holdings", broken_parser)
    report = run_import(engine)
    assert report.status == "failed"
    assert report.safe_error == "import_parse_failed"
    with Session(engine) as session:
        run = session.get(ImportRun, report.run_id)
        assert run.error_code == "import_parse_failed"
        assert "private" not in run.counts_json
        assert session.scalars(select(SourceRecord)).all() == []


def test_clock_records_actual_completion_time_for_a_failed_parse(engine):
    later = NOW + timedelta(minutes=2)
    instants = iter([NOW, later])
    report = run_import(engine, content=b"invalid", clock=lambda: next(instants))
    with Session(engine) as session:
        run = session.get(ImportRun, report.run_id)
        assert run.started_at == NOW
        assert run.finished_at == later


def test_bad_initial_clock_has_safe_error_before_any_operation(engine):
    with pytest.raises(ImportValidationError) as caught:
        run_import(engine, clock=lambda: datetime(2026, 1, 2))
    assert caught.value.code == "clock_must_be_aware"
    with Session(engine) as session:
        assert session.scalars(select(ImportRun)).all() == []
