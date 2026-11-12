"""Exercise the actual migrated role; no hosted credentials or real identities."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_supabase_migration import RUNTIME_SQL_PATH, SQL_PATHS, _execute_native_asset
from test_supabase_migration import native_engine as native_engine

from meridian.persistence.models import Account, AccountMember, AppSession, AuditRecord
from meridian.security.login_limiter import DatabaseLoginLimiter
from meridian.security.sessions import SessionError, SessionService
from meridian.security.supabase_auth import VerifiedIdentity

pytestmark = pytest.mark.postgres
ACCOUNT = "shared-isa"
SUBJECTS = tuple(f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 4))


@pytest.fixture(params=["postgres_engine", "native_engine"])
def runtime(request):
    engine = request.getfixturevalue(request.param)
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    return engine, "meridian_bff_" + schema, schema


def database(engine, role):
    def factory():
        db = Session(engine)

        @event.listens_for(db, "after_begin")
        def restrict(_session, _transaction, connection):
            connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
            assert connection.scalar(text("SELECT current_user")) == role

        return db

    return factory


def test_migrated_role_has_no_elevated_flags_password_parents_or_ownership(runtime):
    engine, role, schema = runtime
    with engine.connect() as connection:
        flags = connection.execute(
            text(
                "SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolinherit,"
                "rolreplication,rolbypassrls,rolpassword IS NULL "
                "FROM pg_authid WHERE rolname=:role"
            ),
            {"role": role},
        ).one()
        assert tuple(flags) == (True, False, False, False, False, False, False, True)
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles "
                    "WHERE rolname=:role)"
                ),
                {"role": role},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_class WHERE relowner=(SELECT oid FROM pg_roles "
                    "WHERE rolname=:role)"
                ),
                {"role": role},
            )
            == 0
        )
        assert connection.scalar(
            text("SELECT has_schema_privilege(:role,:schema,'USAGE')"),
            {"role": role, "schema": schema},
        )
        assert not connection.scalar(
            text("SELECT has_schema_privilege(:role,:schema,'CREATE')"),
            {"role": role, "schema": schema},
        )
        expected = {
            "account_members": {"SELECT"},
            "app_sessions": {"SELECT", "INSERT"},
            "audit_log": {"INSERT"},
            "login_rate_limits": {"SELECT", "INSERT"},
        }
        for table in ("accounts", "source_records", "import_log", "alembic_version", *expected):
            for privilege in (
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "TRUNCATE",
                "REFERENCES",
                "TRIGGER",
            ):
                allowed = connection.scalar(
                    text("SELECT has_table_privilege(:role,:table,:priv)"),
                    {"role": role, "table": f"{schema}.{table}", "priv": privilege},
                )
                assert allowed is (privilege in expected.get(table, set())), (table, privilege)
        for table, columns, writable in (
            (
                "app_sessions",
                (
                    "token_hash",
                    "account_id",
                    "auth_subject",
                    "csrf_hash",
                    "created_at",
                    "expires_at",
                    "revoked_at",
                ),
                {"revoked_at"},
            ),
            (
                "login_rate_limits",
                ("bucket", "window_started_at", "attempts"),
                {"window_started_at", "attempts"},
            ),
        ):
            for column in columns:
                allowed = connection.scalar(
                    text("SELECT has_column_privilege(:role,:table,:column,'UPDATE')"),
                    {"role": role, "table": f"{schema}.{table}", "column": column},
                )
                assert allowed is (column in writable), (table, column)


def test_migrated_role_runs_limiter_before_provisioning_and_both_member_sessions(runtime):
    engine, role, _schema = runtime
    factory = database(engine, role)
    limiter = DatabaseLoginLimiter(factory, "shared-login", max_attempts=2)
    assert limiter.consume() and limiter.consume()
    assert limiter.consume() is False
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.add(Account(id=ACCOUNT, environment="demo"))
        db.flush()
        db.add_all(
            [
                AccountMember(
                    account_id=ACCOUNT,
                    auth_subject=subject,
                    slot=slot,
                    created_at=now - timedelta(seconds=2),
                )
                for slot, subject in enumerate(SUBJECTS[:2], 1)
            ]
        )
    service = SessionService(ACCOUNT, "https://synthetic.example")
    for subject in SUBJECTS[:2]:
        with factory() as db, db.begin():
            issued = service.issue(
                db, VerifiedIdentity(subject, now + timedelta(minutes=5)), now=now
            )
        with factory() as db, db.begin():
            assert service.authenticate(db, issued.token, now=now).subject == subject
            rotated = service.rotate(
                db, issued.token, csrf_token=issued.csrf_token, origin=service.origin, now=now
            )
        with factory() as db, db.begin():
            with pytest.raises(SessionError):
                service.authenticate(db, issued.token, now=now)
            service.revoke(
                db, rotated.token, csrf_token=rotated.csrf_token, origin=service.origin, now=now
            )
    with Session(engine) as db:
        assert len(db.scalars(select(AuditRecord)).all()) == 6
        assert all(row.revoked_at is not None for row in db.scalars(select(AppSession)))


def test_migrated_role_denies_provisioning_other_accounts_and_arbitrary_buckets(runtime):
    engine, role, _schema = runtime
    factory = database(engine, role)
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.add_all(
            [
                Account(id=ACCOUNT, environment="demo"),
                Account(id="other-account", environment="demo"),
            ]
        )
        db.flush()
        db.add(
            AccountMember(
                account_id="other-account",
                auth_subject=SUBJECTS[2],
                slot=1,
                created_at=now - timedelta(seconds=2),
            )
        )
        db.add(
            AccountMember(
                account_id=ACCOUNT,
                auth_subject=SUBJECTS[0],
                slot=1,
                created_at=now - timedelta(seconds=2),
            )
        )
    with factory() as db, db.begin():
        assert len(db.scalars(select(AccountMember)).all()) == 1
        assert db.get(AccountMember, ("other-account", SUBJECTS[2])) is None
        with pytest.raises(SessionError):
            SessionService("other-account", "https://synthetic.example").issue(
                db, VerifiedIdentity(SUBJECTS[2], now + timedelta(minutes=5)), now=now
            )
    forbidden = [
        "SELECT * FROM accounts",
        "SELECT * FROM source_records",
        "SELECT * FROM import_log",
        "SELECT * FROM audit_log",
        "INSERT INTO account_members SELECT * FROM account_members",
        "UPDATE account_members SET revoked_at=NULL",
        "DELETE FROM account_members",
        "DELETE FROM app_sessions",
        "UPDATE app_sessions SET expires_at=created_at",
        "UPDATE audit_log SET action=action",
        "DELETE FROM audit_log",
        "INSERT INTO login_rate_limits VALUES ('arbitrary',0,1)",
        "DELETE FROM login_rate_limits",
        "UPDATE login_rate_limits SET bucket='arbitrary'",
    ]
    for statement in forbidden:
        with pytest.raises(DBAPIError) as caught, factory() as db, db.begin():
            db.execute(text(statement))
        assert caught.value.orig.args[0]["C"] == "42501", statement
    with pytest.raises(DBAPIError) as caught, factory() as db, db.begin():
        db.execute(
            insert(AppSession),
            {
                "token_hash": "a" * 64,
                "csrf_hash": "b" * 64,
                "account_id": "other-account",
                "auth_subject": SUBJECTS[2],
                "created_at": now,
                "expires_at": now + timedelta(minutes=5),
            },
        )
    assert caught.value.orig.args[0]["C"] == "42501"
    for overrides in (
        {"action": "change_settings"},
        {"entity_id": "other-account"},
        {"details_json": '{"unexpected":"input"}'},
    ):
        with pytest.raises(DBAPIError) as caught, factory() as db, db.begin():
            db.execute(
                insert(AuditRecord),
                {
                    "id": "invalid-audit",
                    "occurred_at": now,
                    "actor": SUBJECTS[0],
                    "action": "session_login",
                    "entity_type": "account",
                    "entity_id": ACCOUNT,
                    "details_json": "{}",
                    **overrides,
                },
            )
        assert caught.value.orig.args[0]["C"] == "42501"


def test_native_role_creation_rolls_back_after_a_late_policy_collision(postgres_schema):
    engine = postgres_schema
    _execute_native_asset(engine, paths=SQL_PATHS[:-1])
    with engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        connection.exec_driver_sql(
            "CREATE POLICY meridian_login_update ON login_rate_limits FOR SELECT USING (false)"
        )
    with pytest.raises(DBAPIError):
        _execute_native_asset(engine, paths=(RUNTIME_SQL_PATH,))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        assert not connection.scalar(
            text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:r)"),
            {"r": "meridian_bff_" + schema},
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM pg_policies WHERE schemaname=:s"), {"s": schema}
            )
            == 1
        )


def test_native_rejects_preexisting_role_without_adopting_or_altering_it(postgres_schema):
    engine = postgres_schema
    _execute_native_asset(engine, paths=SQL_PATHS[:-1])
    with engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        role = "meridian_bff_" + schema
        connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
    with pytest.raises(DBAPIError) as caught:
        _execute_native_asset(engine, paths=(RUNTIME_SQL_PATH,))
    assert caught.value.orig.args[0]["C"] == "42710"
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        assert (
            connection.scalar(
                text("SELECT rolcanlogin FROM pg_roles WHERE rolname=:r"), {"r": role}
            )
            is False
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM pg_policies WHERE schemaname=:s"), {"s": schema}
            )
            == 0
        )


def test_password_setup_can_revoke_only_selected_subject_with_migrated_role(runtime):
    engine, role, _schema = runtime
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.add(Account(id=ACCOUNT, environment="demo"))
        db.flush()
        for slot, subject in enumerate(SUBJECTS[:2], 1):
            db.add(
                AccountMember(
                    account_id=ACCOUNT,
                    auth_subject=subject,
                    slot=slot,
                    created_at=now - timedelta(seconds=2),
                )
            )
    factory = database(engine, role)
    service = SessionService(ACCOUNT, "https://synthetic.example")
    issued = []
    for subject in SUBJECTS[:2]:
        with factory() as db, db.begin():
            issued.append(
                service.issue(db, VerifiedIdentity(subject, now + timedelta(minutes=5)), now=now)
            )
    with factory() as db, db.begin():
        identity = VerifiedIdentity(SUBJECTS[0], now + timedelta(minutes=5))
        service.require_member(db, identity, now=now)
        service.revoke_subject(db, identity.subject, now=now)
    with factory() as db, db.begin():
        with pytest.raises(SessionError):
            service.authenticate(db, issued[0].token, now=now)
        assert service.authenticate(db, issued[1].token, now=now).subject == SUBJECTS[1]
    with Session(engine) as db:
        assert len(db.scalars(select(AuditRecord)).all()) == 3
