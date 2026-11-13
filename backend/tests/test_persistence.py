"""Synthetic integration cases for evidence durability and exact SQLite values."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Column, MetaData, Table, insert, inspect, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from meridian.persistence.database import create_db_engine
from meridian.persistence.models import Account, AuditRecord, Base, ImportRun, SourceRecord
from meridian.persistence.types import ExactDecimal, decimal_text

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)
HASH = "a" * 64


def migrate(engine, revision="head"):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)


@pytest.fixture
def engine(tmp_path):
    engine = create_db_engine(tmp_path / "synthetic.db")
    migrate(engine)
    yield engine
    engine.dispose()


def add_account(session, identifier="synthetic-account", environment="demo"):
    account = Account(id=identifier, environment=environment)
    session.add(account)
    session.flush()
    return account


def make_run(identifier="run-1", **overrides):
    fields = dict(
        id=identifier,
        account_id="synthetic-account",
        kind="synthetic_snapshot",
        status="succeeded",
        content_hash=HASH,
        started_at=NOW,
        finished_at=NOW,
    )
    fields.update(overrides)
    return ImportRun(**fields)


def make_source(**overrides):
    fields = dict(
        id="source-1",
        run_id="run-1",
        account_id="synthetic-account",
        kind="synthetic_snapshot",
        row_number=2,
        schema_version="synthetic/v1",
        payload_json='{"quantity":"1.25"}',
        digest="b" * 64,
    )
    fields.update(overrides)
    return SourceRecord(**fields)


def make_audit(**overrides):
    fields = dict(
        id="audit-1",
        occurred_at=NOW,
        actor="system",
        action="import",
        entity_type="import_run",
        entity_id="run-1",
        run_id="run-1",
        details_json="{}",
    )
    fields.update(overrides)
    return AuditRecord(**fields)


def test_migration_from_base_matches_models_and_repeated_upgrade_keeps_evidence(tmp_path):
    engine = create_db_engine(tmp_path / "upgrade.db")
    try:
        migrate(engine, "base")
        assert "accounts" not in inspect(engine).get_table_names()
        migrate(engine)
        with Session(engine) as session, session.begin():
            add_account(session)
            session.add(make_run())
            session.flush()
            session.add(make_source())
        migrate(engine)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() == "0006"
            assert compare_metadata(context, Base.metadata) == []
        with Session(engine) as session:
            assert session.get(SourceRecord, "source-1").payload_json == '{"quantity":"1.25"}'
    finally:
        engine.dispose()


def test_sqlite_pragmas_and_foreign_keys(engine):
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
    with Session(engine) as session:
        session.add(make_run(account_id="missing"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_sqlite_upgrade_from_0001_to_0002_retains_evidence_and_partial_index(tmp_path):
    engine = create_db_engine(tmp_path / "previous-version.db")
    try:
        migrate(engine, "0001")
        with Session(engine) as session, session.begin():
            add_account(session)
            session.add(make_run())
            session.flush()
            session.add(make_source())
        migrate(engine, "0002")
        with Session(engine) as session, session.begin():
            assert session.get(SourceRecord, "source-1").payload_json == '{"quantity":"1.25"}'
            session.add(make_run("failed-retry", status="failed"))
        with engine.connect() as connection:
            index_sql = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name = 'uq_import_accepted_hash'"
            ).scalar_one()
            assert "WHERE status = 'succeeded'" in index_sql
    finally:
        engine.dispose()


def test_sqlite_upgrade_from_0002_adds_closed_auth_without_changing_evidence(tmp_path):
    engine = create_db_engine(tmp_path / "auth-upgrade.db")
    try:
        migrate(engine, "0002")
        with Session(engine) as session, session.begin():
            add_account(session)
            session.add(make_run())
            session.flush()
            session.add(make_source())
        migrate(engine, "0003")
        with engine.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == "0003"
            assert "login_rate_limits" not in inspect(engine).get_table_names()
        with Session(engine) as session:
            assert session.get(SourceRecord, "source-1").payload_json == '{"quantity":"1.25"}'
    finally:
        engine.dispose()


def test_exact_decimal_round_trip_is_text_and_does_not_round_with_context(engine):
    metadata = MetaData()
    amounts = Table("synthetic_amounts", metadata, Column("amount", ExactDecimal(), nullable=False))
    metadata.create_all(engine)
    examples = [
        Decimal("123456789012345678901234567890.12345678901234567890123456789"),
        Decimal("0.000000000000000000000000000000000000123456789"),
        Decimal("-999999999999999999999999999999999999.999999999999999999"),
        Decimal("1E+40"),
        Decimal("-0.0000"),
        Decimal("12.34000"),
    ]
    with localcontext() as context:
        context.prec = 6
        with engine.begin() as connection:
            connection.execute(insert(amounts), [{"amount": amount} for amount in examples])
            assert list(connection.execute(select(amounts.c.amount)).scalars()) == examples
            stored = connection.exec_driver_sql(
                "SELECT typeof(amount), amount FROM synthetic_amounts"
            ).all()
    assert all(storage_type == "text" for storage_type, _ in stored)
    assert stored[-2][1] == "0"
    assert stored[-1][1] == "12.34"
    assert "E" not in stored[3][1]


@pytest.mark.parametrize(
    "value", [0.1, True, Decimal("NaN"), Decimal("Infinity"), "-Infinity", "not a number"]
)
def test_exact_decimal_rejects_unsafe_values(value):
    with pytest.raises((TypeError, ValueError)):
        decimal_text(value)


def test_aware_timestamp_normalizes_to_utc_and_naive_timestamp_is_rejected(engine):
    eastern_time = datetime(2026, 1, 2, 7, tzinfo=timezone(timedelta(hours=-5)))
    with Session(engine) as session, session.begin():
        add_account(session)
        session.add(make_run(started_at=eastern_time))
    with Session(engine) as session:
        loaded = session.get(ImportRun, "run-1")
        assert loaded.started_at == NOW
        assert loaded.started_at.tzinfo is UTC
    with Session(engine) as session:
        session.add(make_run("naive", content_hash=None, started_at=datetime(2026, 1, 2)))
        with pytest.raises(StatementError, match="timezone-aware"):
            session.commit()


def test_successful_hash_is_unique_but_failed_duplicate_and_other_scopes_are_allowed(engine):
    with Session(engine) as session, session.begin():
        add_account(session)
        add_account(session, "other-account", "live")
        session.add_all(
            [
                make_run(),
                make_run("failed", status="failed"),
                make_run("duplicate", status="duplicate"),
                make_run("other-kind", kind="other_snapshot"),
                make_run("other-account-run", account_id="other-account"),
            ]
        )
    with Session(engine) as session:
        session.add(make_run("repeated-success"))
        with pytest.raises(IntegrityError):
            session.commit()
    with Session(engine) as session:
        assert len(session.scalars(select(ImportRun)).all()) == 5


def test_failed_transaction_leaves_no_source_or_audit_rows(engine):
    with Session(engine) as session, session.begin():
        add_account(session)
        session.add(make_run(status="running", finished_at=None))
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with Session(engine) as session, session.begin():
            session.add(make_source())
            session.add(make_audit())
            session.flush()
            raise RuntimeError("synthetic failure")
    with Session(engine) as session:
        assert session.scalars(select(SourceRecord)).all() == []
        assert session.scalars(select(AuditRecord)).all() == []
        assert session.get(ImportRun, "run-1").status == "running"


@pytest.mark.parametrize("model", [SourceRecord, AuditRecord])
@pytest.mark.parametrize("mutation", ["update", "delete"])
def test_evidence_and_audit_orm_mutations_are_rejected(engine, model, mutation):
    with Session(engine) as session, session.begin():
        add_account(session)
        session.add(make_run())
        session.flush()
        session.add_all([make_source(), make_audit()])
    identifier = "source-1" if model is SourceRecord else "audit-1"
    with Session(engine) as session:
        record = session.get(model, identifier)
        if mutation == "delete":
            session.delete(record)
        elif model is SourceRecord:
            record.payload_json = "{}"
        else:
            record.details_json = '{"changed":true}'
        with pytest.raises(ValueError, match="immutable"):
            session.commit()
    with Session(engine) as session:
        record = session.get(model, identifier)
        assert record is not None
        if model is SourceRecord:
            assert record.payload_json == '{"quantity":"1.25"}'
        else:
            assert record.details_json == "{}"


def test_source_row_unique_within_run(engine):
    with Session(engine) as session, session.begin():
        add_account(session)
        session.add(make_run())
        session.flush()
        session.add(make_source())
    with Session(engine) as session:
        session.add(make_source(id="source-2"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_source_cannot_claim_a_different_account_from_its_run(engine):
    with Session(engine) as session, session.begin():
        add_account(session)
        add_account(session, "other-account", "live")
        session.add(make_run())
    with Session(engine) as session:
        session.add(make_source(account_id="other-account"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_invalid_environment_and_currency_are_rejected(engine):
    for environment, currency in [("production", "GBP"), ("demo", "gbp"), ("demo", "GB")]:
        with Session(engine) as session:
            session.add(Account(id="invalid", environment=environment, currency=currency))
            with pytest.raises(IntegrityError):
                session.commit()
