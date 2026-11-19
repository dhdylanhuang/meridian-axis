"""Real PostgreSQL tests for the bounded, least-privilege retention capability."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_supabase_migration import native_engine as native_engine

from meridian.hosted_backup import controls_sql
from meridian.persistence.models import (
    Account,
    AuditRecord,
    BrokerEventRevision,
    BrokerSnapshot,
    ImportRun,
    SourceRecord,
)


@pytest.fixture(params=["postgres_engine", "native_engine"])
def database(request):
    return request.getfixturevalue(request.param)


def seed(db, key, when, account="shared-isa", kind="trading212_refresh"):
    digest = hashlib.sha256(key.encode()).hexdigest()
    db.add(
        ImportRun(
            id=key,
            account_id=account,
            kind=kind,
            status="succeeded",
            content_hash=digest,
            started_at=when,
            finished_at=when,
        )
    )
    db.flush()
    db.add(
        SourceRecord(
            id=key,
            run_id=key,
            account_id=account,
            kind=kind,
            row_number=1,
            schema_version="trading212_sync_v2",
            payload_json='{"exact":"0.1234567890123456789"}',
            digest=digest,
        )
    )
    db.add(
        BrokerSnapshot(
            id=key,
            account_id=account,
            source_run_id=key,
            observed_at=when,
            created_at=when,
            snapshot_json="{}",
            digest=digest,
        )
    )
    db.add(
        AuditRecord(
            id=key,
            occurred_at=when,
            actor="synthetic",
            action="published",
            entity_type="import_run",
            entity_id=key,
            run_id=key,
        )
    )
    db.flush()


def prune(engine):
    with engine.begin() as db:
        schema = db.scalar(text("SELECT current_schema()"))
        db.exec_driver_sql(f'SET LOCAL ROLE "meridian_sync_{schema}"')
        return db.scalar(text("SELECT prune_broker_refresh()"))


@pytest.mark.postgres
def test_preserves_recent_daily_latest_pinned_other_sources_and_audit(database):
    engine = database
    now = datetime.now(UTC)
    old = (now - timedelta(days=90)).replace(hour=10, minute=0, second=0, microsecond=0)
    with Session(engine) as db, db.begin():
        db.add_all(
            [Account(id="shared-isa", environment="live"), Account(id="other", environment="live")]
        )
        db.flush()
        seed(db, "expire", old)
        seed(db, "pin", old + timedelta(seconds=1))
        seed(db, "daily", old + timedelta(hours=1))
        seed(db, "latest", now)
        seed(db, "recent", now - timedelta(days=59))
        seed(db, "foreign", old, account="other")
        seed(db, "initial-capture", old - timedelta(days=1), kind="trading212_capture")
        seed(db, "mixed", old + timedelta(seconds=2))
        db.add(
            SourceRecord(
                id="history",
                run_id="mixed",
                account_id="shared-isa",
                row_number=2,
                kind="trading212_history_page",
                schema_version="v1",
                payload_json='{"cash":"1.23"}',
                digest="a" * 64,
            )
        )
        db.add(
            BrokerEventRevision(
                id="revision",
                account_id="shared-isa",
                family="orders",
                external_id="synthetic",
                revision=1,
                source_id="pin",
                observed_at=old,
                digest="a" * 64,
                payload_json="{}",
                quality="observed",
            )
        )
    result = prune(engine)
    assert result == {"status": "completed", "snapshots_removed": 1, "sources_removed": 1}
    assert prune(engine) == {"status": "already_completed"}
    with Session(engine) as db:
        assert db.get(BrokerSnapshot, "expire") is None
        assert db.get(SourceRecord, "expire") is None
        for key in ["pin", "daily", "latest", "recent", "foreign", "initial-capture", "mixed"]:
            assert db.get(BrokerSnapshot, key) is not None
            assert db.get(SourceRecord, key) is not None
        assert db.get(SourceRecord, "history").payload_json == '{"cash":"1.23"}'
        assert db.get(SourceRecord, "pin").payload_json == '{"exact":"0.1234567890123456789"}'
        assert db.scalar(select(func.count()).select_from(ImportRun)) == 8
        assert db.scalar(select(func.count()).select_from(AuditRecord)) == 9
        assert db.scalar(select(func.count()).select_from(BrokerEventRevision)) == 1
    with engine.connect() as db:
        schema = db.scalar(text("SELECT current_schema()"))
    for role in [f"meridian_bff_{schema}", "anon", "authenticated"]:
        with engine.begin() as db:
            assert not db.scalar(
                text("SELECT has_function_privilege(:role, 'prune_broker_refresh()', 'EXECUTE')"),
                {"role": role},
            )
    with pytest.raises(DBAPIError), engine.begin() as db:
        db.exec_driver_sql(f'SET LOCAL ROLE "meridian_sync_{schema}"')
        db.execute(text("DELETE FROM source_records"))


@pytest.mark.postgres
def test_cleanup_is_capped_at_two_hundred_pairs_and_keeps_daily_anchor(database):
    now = datetime.now(UTC)
    old = (now - timedelta(days=90)).replace(hour=10, minute=0, second=0, microsecond=0)
    with Session(database) as db, db.begin():
        db.add(Account(id="shared-isa", environment="live"))
        db.flush()
        for i in range(205):
            seed(db, f"old-{i:03d}", old + timedelta(seconds=i))
    assert prune(database)["snapshots_removed"] == 200
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(BrokerSnapshot)) == 5
        assert db.get(BrokerSnapshot, "old-204") is not None
        assert db.scalar(select(func.count()).select_from(SourceRecord)) == 5
        assert db.scalar(select(func.count()).select_from(ImportRun)) == 205
        assert db.scalar(select(func.count()).select_from(AuditRecord)) == 206


def test_native_function_asset_and_backup_head_contract():
    root = Path(__file__).resolve().parents[2]
    body = (root / "backend/migrations/sql/0008_refresh_retention.sql").read_text()
    native = (root / "supabase/migrations/20261119000100_refresh_retention.sql").read_text()
    assert native.count(body) == 1
    assert "DELETE FROM" not in native[: native.index(body)]
    assert "public.broker_event_revisions" in controls_sql("0008")
