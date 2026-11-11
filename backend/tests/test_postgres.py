"""PostgreSQL parity on isolated schemas in an explicit disposable test database.

Network-free configuration tests always run. Marked integration tests require
MERIDIAN_TEST_POSTGRES_URL and accept a loopback PostgreSQL service only. They
create/drop only their own generated schema, never migrate public tables.
"""

import os
import re
import ssl
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Column, MetaData, Table, event, insert, make_url, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateIndex, CreateSchema, DropSchema

from meridian.application.imports import import_holdings
from meridian.persistence import postgres
from meridian.persistence.models import Account, AuditRecord, Base, ImportRun, SourceRecord
from meridian.persistence.postgres import (
    PostgresConfigurationError,
    PostgresOperationError,
    create_postgres_engine,
    upgrade_postgres_database,
)
from meridian.persistence.types import ExactDecimal

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)
SYNTHETIC_URL = "postgresql+pg8000://synthetic:invented-password@database.invalid/test"
_OWN_SCHEMA = re.compile(r"meridian_test_[0-9a-f]{32}\Z")
_TABLES = ("accounts", "import_log", "source_records", "audit_log")


@pytest.mark.parametrize(
    "url,code",
    [
        ("invalid-url-with-invented-password", "postgres_url_invalid"),
        ("sqlite:///synthetic.db", "postgres_driver_invalid"),
        ("postgresql://synthetic:invented-password@localhost/test", "postgres_driver_invalid"),
        ("postgresql+pg8000://synthetic@/test", "postgres_url_incomplete"),
        (SYNTHETIC_URL + "?ssl_context=false", "postgres_url_options_unsupported"),
    ],
)
def test_unsafe_database_configuration_has_safe_errors(url, code):
    with pytest.raises(PostgresConfigurationError) as caught:
        create_postgres_engine(url)
    assert caught.value.code == code
    assert str(caught.value) == code
    assert "invented-password" not in str(caught.value)


def test_engine_defaults_to_verified_tls_nullpool_and_hidden_parameters(monkeypatch):
    captured = {}
    sentinel = object()

    def capture(url, **options):
        captured["url"] = url
        captured.update(options)
        return sentinel

    monkeypatch.setattr(postgres, "create_engine", capture)
    assert create_postgres_engine(SYNTHETIC_URL) is sentinel
    tls = captured["connect_args"]["ssl_context"]
    assert isinstance(tls, ssl.SSLContext)
    assert tls.check_hostname is True
    assert tls.verify_mode == ssl.CERT_REQUIRED
    assert captured["connect_args"]["timeout"] == 10
    assert captured["poolclass"] is NullPool
    assert captured["hide_parameters"] is True
    assert captured["client_encoding"] == "utf8"


def test_insecure_exception_is_explicit_and_loopback_only(monkeypatch):
    captured = {}

    def capture(_url, **options):
        captured.update(options)
        return object()

    monkeypatch.setattr(postgres, "create_engine", capture)
    local_url = "postgresql+pg8000://synthetic:invented-password@127.0.0.1/test"
    create_postgres_engine(local_url, allow_loopback_insecure=True)
    assert captured["connect_args"]["ssl_context"] is False
    with pytest.raises(PostgresConfigurationError, match="insecure_host_forbidden"):
        create_postgres_engine(SYNTHETIC_URL, allow_loopback_insecure=True)


def test_engine_creation_exception_never_exposes_url_or_driver_details(monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError(SYNTHETIC_URL)

    monkeypatch.setattr(postgres, "create_engine", fail)
    with pytest.raises(PostgresConfigurationError) as caught:
        create_postgres_engine(SYNTHETIC_URL)
    assert str(caught.value) == "postgres_engine_unavailable"
    assert caught.value.__suppress_context__ is True


def test_migration_uses_supplied_connection_and_safe_failure(monkeypatch):
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    connection = engine.begin.return_value.__enter__.return_value

    def fail(config, revision):
        assert config.attributes["connection"] is connection
        assert config.get_main_option("sqlalchemy.url") is None
        assert revision == "head"
        raise RuntimeError(SYNTHETIC_URL)

    monkeypatch.setattr(postgres.command, "upgrade", fail)
    with pytest.raises(PostgresOperationError) as caught:
        upgrade_postgres_database(engine)
    assert str(caught.value) == "postgres_migration_failed"
    assert caught.value.__suppress_context__ is True


def test_postgres_migration_rejects_another_dialect():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    with pytest.raises(PostgresConfigurationError, match="postgres_engine_required"):
        upgrade_postgres_database(engine)


def test_model_compiles_accepted_hash_as_a_postgres_partial_index():
    index = next(
        index for index in ImportRun.__table__.indexes if index.name == "uq_import_accepted_hash"
    )
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "UNIQUE INDEX" in ddl
    assert "WHERE status = 'succeeded' AND content_hash IS NOT NULL" in ddl


@pytest.fixture
def postgres_schema():
    supplied_url = os.environ.get("MERIDIAN_TEST_POSTGRES_URL")
    if not supplied_url:
        pytest.skip("Set MERIDIAN_TEST_POSTGRES_URL to an explicitly disposable loopback database")
    try:
        url = make_url(supplied_url)
    except Exception:
        pytest.fail("PostgreSQL test URL is invalid", pytrace=False)
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail(
            "PostgreSQL integration tests require a disposable loopback server", pytrace=False
        )
    admin = create_postgres_engine(url, allow_loopback_insecure=True)
    schema = "meridian_test_" + uuid4().hex
    if not _OWN_SCHEMA.fullmatch(schema):
        raise AssertionError("Unsafe generated test schema")
    engine = None
    created = False
    try:
        try:
            with admin.begin() as connection:
                connection.execute(CreateSchema(schema))
            created = True
        except Exception:
            pytest.fail(
                "Disposable PostgreSQL database is unavailable or cannot create test schemas",
                pytrace=False,
            )
        engine = create_postgres_engine(url, allow_loopback_insecure=True)

        @event.listens_for(engine, "connect", insert=True)
        def select_isolated_schema(dbapi_connection, _record):
            # Set before dialect initialization, outside a transaction, so both
            # reflection and later rollback use only this generated schema.
            previous = dbapi_connection.autocommit
            dbapi_connection.autocommit = True
            try:
                cursor = dbapi_connection.cursor()
                try:
                    cursor.execute(f'SET SESSION search_path TO "{schema}"')
                finally:
                    cursor.close()
            finally:
                dbapi_connection.autocommit = previous

        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            # This is the sole cascading cleanup and its target was generated,
            # validated and created by this fixture. Never drop public objects.
            assert _OWN_SCHEMA.fullmatch(schema)
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


@pytest.fixture
def postgres_engine(postgres_schema):
    _migrate_test_schema(postgres_schema)
    return postgres_schema


def _migrate_test_schema(engine, *, revision="head"):
    try:
        upgrade_postgres_database(engine, revision=revision)
    except PostgresOperationError as exc:
        # This fixture only accepts a disposable loopback server and invented
        # data. Expose its underlying DDL error for CI diagnosis; production
        # callers still receive only the safe operation category.
        pytest.fail(f"Disposable migration failed: {exc.__context__!r}", pytrace=False)


def _account(session, identifier="synthetic-account", environment="demo"):
    session.add(Account(id=identifier, environment=environment))
    session.flush()


def _run(identifier="run-1", **overrides):
    return ImportRun(
        **(
            {
                "id": identifier,
                "account_id": "synthetic-account",
                "kind": "synthetic_snapshot",
                "status": "succeeded",
                "content_hash": "a" * 64,
                "started_at": NOW,
                "finished_at": NOW,
            }
            | overrides
        )
    )


def _source(**overrides):
    return SourceRecord(
        **(
            {
                "id": "source-1",
                "run_id": "run-1",
                "account_id": "synthetic-account",
                "kind": "synthetic_snapshot",
                "row_number": 2,
                "schema_version": "synthetic/v1",
                "payload_json": '{"quantity":"1.25"}',
                "digest": "b" * 64,
            }
            | overrides
        )
    )


@pytest.mark.postgres
def test_postgres_upgrade_preserves_0001_evidence_and_fixes_retry_index(postgres_schema):
    engine = postgres_schema
    _migrate_test_schema(engine, revision="0001")
    with Session(engine) as session, session.begin():
        _account(session)
        session.add(_run())
        session.flush()
        session.add(_source())
    with engine.begin() as connection:
        for table in _TABLES:
            connection.execute(text(f'GRANT ALL PRIVILEGES ON TABLE "{table}" TO PUBLIC'))
        # Optional Supabase-like roles are never created or modified globally.
        # If CI supplies them, seed table grants so the migration must remove them.
        for role in ("anon", "authenticated"):
            exists = connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role": role}
            )
            if exists:
                for table in _TABLES:
                    connection.execute(text(f'GRANT ALL PRIVILEGES ON TABLE "{table}" TO "{role}"'))
    _migrate_test_schema(engine)
    with Session(engine) as session, session.begin():
        assert session.get(SourceRecord, "source-1").payload_json == '{"quantity":"1.25"}'
        session.add_all(
            [_run("failed-retry", status="failed"), _run("duplicate", status="duplicate")]
        )
    _assert_private_tables(engine)


@pytest.mark.postgres
def test_postgres_fresh_migration_matches_models(postgres_engine):
    with postgres_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == "0002"
        assert compare_metadata(context, Base.metadata) == []
    _assert_private_tables(postgres_engine)


def _assert_private_tables(engine):
    with engine.connect() as connection:
        states = dict(
            connection.execute(
                text(
                    "SELECT c.relname,c.relrowsecurity FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname=current_schema() "
                    "AND c.relname IN ('accounts','import_log','source_records','audit_log')"
                )
            ).all()
        )
        assert states == dict.fromkeys(_TABLES, True)
        forbidden_grants = connection.execute(
            text(
                "SELECT c.relname,e.grantee FROM pg_class c JOIN pg_namespace n "
                "ON n.oid=c.relnamespace CROSS JOIN LATERAL "
                "aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) e "
                "WHERE n.nspname=current_schema() "
                "AND c.relname IN ('accounts','import_log','source_records','audit_log') "
                "AND (e.grantee=0 OR e.grantee IN "
                "(SELECT oid FROM pg_roles WHERE rolname IN ('anon','authenticated')))"
            )
        ).all()
        assert forbidden_grants == []
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_policies WHERE schemaname=current_schema() "
                    "AND tablename IN ('accounts','import_log','source_records','audit_log')"
                )
            )
            == 0
        )


@pytest.mark.postgres
def test_postgres_success_hash_uniqueness_and_retry_attempts(postgres_engine):
    with Session(postgres_engine) as session, session.begin():
        _account(session)
        session.add_all(
            [
                _run(),
                _run("failed", status="failed"),
                _run("duplicate", status="duplicate"),
                _run("running", status="running", finished_at=None),
            ]
        )
    with Session(postgres_engine) as session:
        session.add(_run("repeated-success"))
        with pytest.raises(IntegrityError):
            session.commit()
    with Session(postgres_engine) as session:
        assert len(session.scalars(select(ImportRun)).all()) == 4


@pytest.mark.postgres
def test_postgres_source_cannot_claim_another_accounts_run(postgres_engine):
    with Session(postgres_engine) as session, session.begin():
        _account(session)
        _account(session, "another-account", "live")
        session.add(_run())
    with Session(postgres_engine) as session:
        session.add(_source(account_id="another-account"))
        # pg8000 maps only unique violations (23505) to IntegrityError; its
        # foreign-key violations are ProgrammingError. Assert the database's
        # precise SQLSTATE and constraint instead of weakening the invariant.
        with pytest.raises(DBAPIError) as caught:
            session.commit()
        detail = caught.value.orig.args[0]
        assert detail["C"] == "23503"
        assert detail["n"] == "fk_source_run_account"


@pytest.mark.postgres
def test_postgres_decimal_text_retains_all_digits(postgres_engine):
    metadata = MetaData()
    amounts = Table(
        "synthetic_decimal_check", metadata, Column("quantity", ExactDecimal(), nullable=False)
    )
    metadata.create_all(postgres_engine)
    expected = Decimal("123456789012345678901234567890.12345678901234567890123456789")
    with localcontext() as context:
        context.prec = 6
        with postgres_engine.begin() as connection:
            connection.execute(insert(amounts), {"quantity": expected})
            assert connection.scalar(select(amounts.c.quantity)) == expected
            raw = connection.scalar(text("SELECT quantity FROM synthetic_decimal_check"))
            assert raw == str(expected)
            assert (
                connection.scalar(
                    text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_schema=current_schema() "
                        "AND table_name='synthetic_decimal_check' "
                        "AND column_name='quantity'"
                    )
                )
                == "text"
            )


def _snapshot_bytes():
    return (
        b"Slice,Name,Invested value,Value,Result,Owned quantity,"
        b"Dividends gained,Dividends cash,Dividends reinvested\r\n"
        b"SYN,Invented Holding,10,12,2,0.125,N/A,N/A,N/A\r\n"
        b"Total,Invented Group,10,12,2,-,5,1,2\r\n"
    )


@pytest.mark.postgres
def test_postgres_import_atomic_rollback_and_successful_retry(postgres_engine):
    with Session(postgres_engine) as session, session.begin():
        _account(session)

    def fail_after_insert(_mapper, _connection, _target):
        raise RuntimeError("synthetic failure after write")

    arguments = {
        "account_id": "synthetic-account",
        "content": _snapshot_bytes(),
        "currency": "GBP",
        "observed_at": NOW,
        "clock": lambda: NOW,
    }
    event.listen(SourceRecord, "after_insert", fail_after_insert)
    try:
        failed = import_holdings(postgres_engine, **arguments)
    finally:
        event.remove(SourceRecord, "after_insert", fail_after_insert)
    assert failed.status == "failed"
    with Session(postgres_engine) as session:
        assert session.get(ImportRun, failed.run_id).status == "failed"
        assert session.scalars(select(SourceRecord)).all() == []
        assert session.scalars(select(AuditRecord)).all() == []
    accepted = import_holdings(postgres_engine, **arguments)
    duplicate = import_holdings(postgres_engine, **arguments)
    assert accepted.status == "succeeded"
    assert duplicate.status == "duplicate"
    with Session(postgres_engine) as session:
        assert len(session.scalars(select(SourceRecord)).all()) == 2
        assert len(session.scalars(select(AuditRecord)).all()) == 1
