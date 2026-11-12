"""Execute the checked-in hosted SQL unchanged in disposable isolated schemas."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect, select, text
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex, CreateTable
from test_postgres import postgres_schema as postgres_schema

from meridian.application.imports import import_holdings
from meridian.persistence.models import Account, AuditRecord, Base, ImportRun, SourceRecord

SQL_PATH = (
    Path(__file__).resolve().parents[2]
    / "supabase/migrations/20261111000100_evidence_foundation.sql"
)
AUTH_SQL_PATH = SQL_PATH.with_name("20261112000100_membership_sessions.sql")
LIMIT_SQL_PATH = SQL_PATH.with_name("20261112000200_login_rate_limits.sql")
RUNTIME_SQL_PATH = SQL_PATH.with_name("20261112000300_runtime_permissions.sql")
RUNTIME_DCL_PATH = (
    Path(__file__).resolve().parents[1] / "migrations/sql/0005_runtime_permissions.sql"
)
SQL_PATHS = (SQL_PATH, AUTH_SQL_PATH, LIMIT_SQL_PATH, RUNTIME_SQL_PATH)
NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)
_TABLES = (
    "accounts",
    "import_log",
    "source_records",
    "audit_log",
    "account_members",
    "app_sessions",
    "login_rate_limits",
    "alembic_version",
)
_OWN_SCHEMA = re.compile(r"meridian_test_[0-9a-f]{32}\Z")


def _space_normalized(value):
    return " ".join(value.split())


def test_checked_in_supabase_table_and_index_ddl_matches_authoritative_models():
    # This fast contract check catches drift in the checked-in bootstrap. Actual
    # PostgreSQL execution, constraints and privileges are verified separately.
    actual = _space_normalized("\n".join(path.read_text(encoding="utf-8") for path in SQL_PATHS))
    pg = dialect()
    for table in Base.metadata.sorted_tables:
        assert _space_normalized(str(CreateTable(table).compile(dialect=pg))) in actual
        for index in table.indexes:
            assert _space_normalized(str(CreateIndex(index).compile(dialect=pg))) in actual


def test_native_runtime_dcl_is_the_exact_immutable_alembic_asset():
    body = RUNTIME_DCL_PATH.read_text(encoding="utf-8")
    native = RUNTIME_SQL_PATH.read_text(encoding="utf-8")
    assert native.count(body) == 1
    assert "alembic_version" not in body
    assert native.index("version_num = '0004'") < native.index(body)
    assert native.index("UPDATE alembic_version SET version_num = '0005'") > native.index(body)


def _execute_native_asset(engine, paths=SQL_PATHS):
    with engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        assert _OWN_SCHEMA.fullmatch(schema)
        # Execute the actual asset, without replacement, splitting or generated
        # substitute DDL. The fixture's trusted search_path confines every object.
        for path in paths:
            connection.exec_driver_sql(path.read_text(encoding="utf-8"))
        assert connection.scalar(text("SELECT current_schema()")) == schema


@pytest.fixture
def native_engine(postgres_schema):
    _execute_native_asset(postgres_schema)
    return postgres_schema


@pytest.mark.postgres
def test_native_supabase_bootstrap_has_exact_schema_head_and_no_seeded_finances(native_engine):
    assert set(inspect(native_engine).get_table_names()) == set(_TABLES)
    with native_engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == "0005"
        assert compare_metadata(context, Base.metadata) == []
        for table in _TABLES[:-1]:
            assert connection.scalar(text(f'SELECT count(*) FROM "{table}"')) == 0
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all() == ["0005"]


@pytest.mark.postgres
def test_native_supabase_asset_removes_default_public_and_existing_api_role_grants(postgres_schema):
    engine = postgres_schema
    with engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        assert _OWN_SCHEMA.fullmatch(schema)
        connection.exec_driver_sql(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT ALL ON TABLES TO PUBLIC'
        )
        for role in ("anon", "authenticated"):
            exists = connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=:role)"), {"role": role}
            )
            if exists:
                connection.exec_driver_sql(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT ALL ON TABLES TO "{role}"'
                )
    _execute_native_asset(engine)
    with engine.connect() as connection:
        states = dict(
            connection.execute(
                text(
                    "SELECT c.relname,c.relrowsecurity FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND c.relkind='r'"
                )
            ).all()
        )
        assert states == dict.fromkeys(_TABLES, True)
        forbidden_grants = connection.execute(
            text(
                "SELECT c.relname,e.grantee FROM pg_class c JOIN pg_namespace n "
                "ON n.oid=c.relnamespace CROSS JOIN LATERAL "
                "aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) e "
                "WHERE n.nspname=current_schema() AND c.relkind='r' "
                "AND (e.grantee=0 OR e.grantee IN "
                "(SELECT oid FROM pg_roles WHERE rolname IN ('anon','authenticated')))"
            )
        ).all()
        assert forbidden_grants == []
        policies = connection.execute(
            text("SELECT tablename, policyname FROM pg_policies WHERE schemaname=current_schema()")
        ).all()
        assert set(policies) == {
            ("account_members", "meridian_member_read"),
            ("app_sessions", "meridian_session_read"),
            ("app_sessions", "meridian_session_insert"),
            ("app_sessions", "meridian_session_revoke"),
            ("audit_log", "meridian_session_audit"),
            ("login_rate_limits", "meridian_login_read"),
            ("login_rate_limits", "meridian_login_insert"),
            ("login_rate_limits", "meridian_login_update"),
        }
        assert (
            connection.scalar(
                text(
                    "SELECT bool_and(p.polroles = ARRAY[(SELECT oid FROM pg_roles "
                    "WHERE rolname = 'meridian_bff_' || current_schema())]::oid[]) "
                    "FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema()"
                )
            )
            is True
        )


@pytest.mark.postgres
def test_native_supabase_conflicting_existing_table_fails_and_all_new_ddl_rolls_back(
    postgres_schema,
):
    engine = postgres_schema
    # The marker is created last by the asset. A conflict there forces earlier
    # native table/index DDL to roll back instead of silently adopting any table.
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
        )
        connection.exec_driver_sql("INSERT INTO alembic_version VALUES ('preexisting-unreviewed')")
    with pytest.raises(DBAPIError) as caught:
        _execute_native_asset(engine)
    assert caught.value.orig.args[0]["C"] == "42P07"
    assert inspect(engine).get_table_names() == ["alembic_version"]
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "preexisting-unreviewed"
        )


@pytest.mark.postgres
def test_native_membership_upgrade_conflict_rolls_back_new_tables_and_keeps_0002(postgres_schema):
    engine = postgres_schema
    _execute_native_asset(engine, paths=(SQL_PATH,))
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE app_sessions (marker TEXT)")
        connection.exec_driver_sql("INSERT INTO app_sessions VALUES ('preexisting')")
    with pytest.raises(DBAPIError) as caught:
        _execute_native_asset(engine, paths=(AUTH_SQL_PATH,))
    assert caught.value.orig.args[0]["C"] == "42P07"
    assert "account_members" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
        assert connection.scalar(text("SELECT marker FROM app_sessions")) == "preexisting"


@pytest.mark.postgres
def test_native_membership_upgrade_preserves_existing_source_evidence(postgres_schema):
    engine = postgres_schema
    _execute_native_asset(engine, paths=(SQL_PATH,))
    with Session(engine) as session, session.begin():
        session.add(Account(id="synthetic-account", environment="demo"))
    outcome = import_holdings(
        engine,
        account_id="synthetic-account",
        content=(
            b"Slice,Name,Invested value,Value,Result,Owned quantity,"
            b"Dividends gained,Dividends cash,Dividends reinvested\r\n"
            b"SYN,Invented Holding,10,12,2,0.125,N/A,N/A,N/A\r\n"
            b"Total,Invented Group,10,12,2,-,5,1,2\r\n"
        ),
        currency="GBP",
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert outcome.status == "succeeded"
    with Session(engine) as session:
        before = [
            (row.id, row.digest, row.payload_json) for row in session.scalars(select(SourceRecord))
        ]
    _execute_native_asset(engine, paths=(AUTH_SQL_PATH,))
    with Session(engine) as session:
        after = [
            (row.id, row.digest, row.payload_json) for row in session.scalars(select(SourceRecord))
        ]
        assert sorted(after) == sorted(before)
    with engine.connect() as connection:
        assert MigrationContext.configure(connection).get_current_revision() == "0003"
        assert "login_rate_limits" not in inspect(engine).get_table_names()


@pytest.mark.postgres
def test_native_limiter_conflict_preserves_0003_and_existing_table(postgres_schema):
    engine = postgres_schema
    _execute_native_asset(engine, paths=(SQL_PATH, AUTH_SQL_PATH))
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE login_rate_limits (marker TEXT)")
        connection.exec_driver_sql("INSERT INTO login_rate_limits VALUES ('preexisting')")
    with pytest.raises(DBAPIError) as caught:
        _execute_native_asset(engine, paths=(LIMIT_SQL_PATH,))
    assert caught.value.orig.args[0]["C"] == "42P07"
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003"
        assert connection.scalar(text("SELECT marker FROM login_rate_limits")) == "preexisting"


@pytest.mark.postgres
def test_native_limiter_wrong_revision_rolls_back_new_table(postgres_schema):
    engine = postgres_schema
    _execute_native_asset(engine, paths=(SQL_PATH,))
    with pytest.raises(DBAPIError):
        _execute_native_asset(engine, paths=(LIMIT_SQL_PATH,))
    assert "login_rate_limits" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002"


@pytest.mark.postgres
def test_native_supabase_import_keeps_atomic_failure_and_replay_guarantees(native_engine):
    with Session(native_engine) as session, session.begin():
        session.add(Account(id="synthetic-account", environment="demo"))
    content = (
        b"Slice,Name,Invested value,Value,Result,Owned quantity,"
        b"Dividends gained,Dividends cash,Dividends reinvested\r\n"
        b"SYN,Invented Holding,10.123,12.123,2,0.125,N/A,N/A,N/A\r\n"
        b"Total,Invented Group,10.123,12.123,2,-,5,1,2\r\n"
    )
    arguments = {
        "account_id": "synthetic-account",
        "content": content,
        "currency": "GBP",
        "observed_at": NOW,
        "clock": lambda: NOW,
    }

    def fail_after_write(_mapper, _connection, _target):
        raise RuntimeError("invented failed write")

    event.listen(SourceRecord, "after_insert", fail_after_write)
    try:
        failed = import_holdings(native_engine, **arguments)
    finally:
        event.remove(SourceRecord, "after_insert", fail_after_write)
    assert failed.status == "failed"
    with Session(native_engine) as session:
        assert session.get(ImportRun, failed.run_id).status == "failed"
        assert session.scalars(select(SourceRecord)).all() == []
        assert session.scalars(select(AuditRecord)).all() == []
    accepted = import_holdings(native_engine, **arguments)
    duplicate = import_holdings(native_engine, **arguments)
    assert accepted.status == "succeeded"
    assert duplicate.status == "duplicate"
    with Session(native_engine) as session:
        assert len(session.scalars(select(SourceRecord)).all()) == 2
        assert len(session.scalars(select(AuditRecord)).all()) == 1
        assert sorted(session.scalars(select(ImportRun.status)).all()) == [
            "duplicate",
            "failed",
            "succeeded",
        ]
