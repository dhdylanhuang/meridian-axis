"""Closed limiter schema, with no production bucket or account provisioning."""

from datetime import UTC, datetime, timedelta

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import insert, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_auth_persistence import auth_engine as auth_engine
from test_persistence import add_account, make_run, make_source, migrate
from test_persistence import engine as engine
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_supabase_migration import (
    AUTH_SQL_PATH,
    LIMIT_SQL_PATH,
    SQL_PATH,
    _execute_native_asset,
)
from test_supabase_migration import native_engine as native_engine

from meridian.persistence.database import create_db_engine
from meridian.persistence.models import AccountMember, AppSession, Base, LoginRateLimit

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)


def test_login_rate_schema_keeps_big_epoch_and_counter_boundaries(auth_engine):
    with auth_engine.begin() as connection:
        connection.execute(
            insert(LoginRateLimit),
            [
                {"bucket": "a", "window_started_at": 0, "attempts": 1},
                {"bucket": "b" * 64, "window_started_at": 2**40, "attempts": 1000},
            ],
        )
    with auth_engine.connect() as connection:
        assert connection.execute(select(LoginRateLimit).order_by(LoginRateLimit.bucket)).all() == [
            ("a", 0, 1),
            ("b" * 64, 2**40, 1000),
        ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"bucket": ""},
        {"bucket": "b" * 65},
        {"window_started_at": -1},
        {"attempts": 0},
        {"attempts": 1001},
    ],
)
def test_login_rate_schema_rejects_invalid_boundaries(auth_engine, overrides):
    with pytest.raises(DBAPIError), auth_engine.begin() as connection:
        connection.execute(
            insert(LoginRateLimit),
            {"bucket": "synthetic", "window_started_at": 0, "attempts": 1} | overrides,
        )


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param("alembic", marks=pytest.mark.postgres),
        pytest.param("native", marks=pytest.mark.postgres),
    ]
)
def prior_schema(request, tmp_path):
    if request.param == "sqlite":
        database = create_db_engine(tmp_path / "previous-limiter.sqlite3")
        migrate(database, "0003")
    else:
        database = request.getfixturevalue("postgres_schema")
        if request.param == "native":
            _execute_native_asset(database, paths=(SQL_PATH, AUTH_SQL_PATH))
        else:
            migrate(database, "0003")
    try:
        yield database, request.param
    finally:
        if request.param == "sqlite":
            database.dispose()


def _previous_rows(database):
    with database.connect() as connection:
        return {
            table.name: connection.execute(select(table).order_by(*table.primary_key.columns)).all()
            for table in Base.metadata.sorted_tables
            if table.name != "login_rate_limits"
        }


def test_limiter_upgrade_preserves_existing_evidence_membership_and_sessions(prior_schema):
    database, path = prior_schema
    subject = "11111111-1111-4111-8111-111111111111"
    with Session(database) as db, db.begin():
        add_account(db)
        db.add(make_run())
        db.flush()
        db.add(make_source())
        db.add(
            AccountMember(
                account_id="synthetic-account",
                auth_subject=subject,
                slot=1,
                created_at=NOW,
            )
        )
        db.flush()
        db.add(
            AppSession(
                token_hash="a" * 64,
                csrf_hash="b" * 64,
                account_id="synthetic-account",
                auth_subject=subject,
                created_at=NOW,
                expires_at=NOW + timedelta(hours=1),
            )
        )
    before = _previous_rows(database)
    if path == "native":
        _execute_native_asset(database, paths=(LIMIT_SQL_PATH,))
    else:
        migrate(database, "0004")
    assert _previous_rows(database) == before
    with database.connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == "0004"
        assert compare_metadata(context, Base.metadata) == []
        assert connection.execute(select(LoginRateLimit)).all() == []
