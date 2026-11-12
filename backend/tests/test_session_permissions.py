"""Disposable trusted-BFF permission candidate; no hosted policies or role changes."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema

from meridian.persistence.models import Account, AccountMember, AppSession, AuditRecord
from meridian.security.sessions import SessionError, SessionService
from meridian.security.supabase_auth import VerifiedIdentity

pytestmark = pytest.mark.postgres
ACCOUNT, OTHER_ACCOUNT = "synthetic-permission-account", "synthetic-other-account"
ORIGIN = "https://synthetic.example"
SUBJECTS = tuple(f"00000000-0000-4000-8000-{number:012d}" for number in range(1, 4))


@pytest.fixture
def permissions(postgres_engine):
    engine = postgres_engine
    now = datetime.now(UTC)
    role = "meridian_bff_test_" + uuid4().hex
    created = False
    policies = []
    try:
        with engine.begin() as connection:
            schema = connection.scalar(text("SELECT current_schema()"))
            assert schema.startswith("meridian_test_") and len(schema) == 46
            connection.exec_driver_sql(
                f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                "NOINHERIT NOBYPASSRLS"
            )
        created = True
        with engine.begin() as connection:
            connection.execute(
                insert(Account),
                [
                    {"id": ACCOUNT, "environment": "demo"},
                    {"id": OTHER_ACCOUNT, "environment": "live"},
                ],
            )
            connection.execute(
                insert(AccountMember),
                [
                    {
                        "account_id": account,
                        "auth_subject": subject,
                        "slot": slot,
                        "created_at": now,
                    }
                    for account, subject, slot in (
                        (ACCOUNT, SUBJECTS[0], 1),
                        (ACCOUNT, SUBJECTS[1], 2),
                        (OTHER_ACCOUNT, SUBJECTS[2], 1),
                    )
                ],
            )
            connection.execute(
                insert(AppSession),
                {
                    "token_hash": "f" * 64,
                    "csrf_hash": "e" * 64,
                    "account_id": OTHER_ACCOUNT,
                    "auth_subject": SUBJECTS[2],
                    "created_at": now,
                    "expires_at": now + timedelta(hours=1),
                },
            )
            connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"')
            connection.exec_driver_sql(f'GRANT SELECT ON account_members, app_sessions TO "{role}"')
            connection.exec_driver_sql(f'GRANT INSERT ON app_sessions, audit_log TO "{role}"')
            connection.exec_driver_sql(f'GRANT UPDATE (revoked_at) ON app_sessions TO "{role}"')

            member = (
                f"account_id = '{ACCOUNT}' AND revoked_at IS NULL "
                "AND created_at::timestamptz <= statement_timestamp()"
            )
            active = (
                f"account_id = '{ACCOUNT}' AND EXISTS (SELECT 1 FROM "
                f'"{schema}".account_members m WHERE m.account_id = app_sessions.account_id '
                "AND m.auth_subject = app_sessions.auth_subject AND m.revoked_at IS NULL)"
            )
            audit = (
                f"entity_id = '{ACCOUNT}' AND entity_type = 'account' AND run_id IS NULL "
                "AND action IN ('session_login', 'session_rotate', 'session_logout') "
                "AND details_json = '{}' AND EXISTS (SELECT 1 FROM "
                f'"{schema}".account_members m WHERE m.account_id = audit_log.entity_id '
                "AND m.auth_subject = audit_log.actor AND m.revoked_at IS NULL)"
            )
            definitions = [
                ("account_members", "member_read", f"FOR SELECT USING ({member})"),
                # Revoked rows remain visible so conditional consumption can
                # write revoked_at without violating UPDATE's SELECT policy.
                ("app_sessions", "session_read", f"FOR SELECT USING ({active})"),
                ("app_sessions", "session_insert", f"FOR INSERT WITH CHECK ({active})"),
                (
                    "app_sessions",
                    "session_revoke",
                    f"FOR UPDATE USING ({active} AND revoked_at IS NULL) WITH CHECK ({active})",
                ),
                ("audit_log", "audit_insert", f"FOR INSERT WITH CHECK ({audit})"),
            ]
            for table, name, clause in definitions:
                # TO precedes USING/WITH CHECK, after the command specification.
                command, condition = clause.split(" ", 2)[1:]
                connection.exec_driver_sql(
                    f'CREATE POLICY "{name}" ON "{table}" FOR {command} TO "{role}" {condition}'
                )
                policies.append((table, name))
        yield engine, role, now
    finally:
        if created:
            with engine.begin() as connection:
                for table, name in policies:
                    connection.exec_driver_sql(f'DROP POLICY IF EXISTS "{name}" ON "{table}"')
                connection.exec_driver_sql(
                    "REVOKE ALL PRIVILEGES ON account_members, app_sessions, audit_log "
                    f'FROM "{role}"'
                )
                connection.exec_driver_sql(
                    f'REVOKE UPDATE (revoked_at) ON app_sessions FROM "{role}"'
                )
                connection.exec_driver_sql(f'REVOKE USAGE ON SCHEMA "{schema}" FROM "{role}"')
                connection.exec_driver_sql(f'DROP ROLE "{role}"')


@contextmanager
def _restricted(engine, role):
    with Session(engine) as db, db.begin():
        db.execute(text(f'SET LOCAL ROLE "{role}"'))
        assert db.scalar(text("SELECT current_user")) == role
        yield db


def test_restricted_bff_runs_both_members_session_lifecycle_and_atomic_audit(permissions):
    engine, role, now = permissions
    service = SessionService(ACCOUNT, ORIGIN)
    for subject in SUBJECTS[:2]:
        with _restricted(engine, role) as db:
            issued = service.issue(db, VerifiedIdentity(subject, now + timedelta(hours=1)), now=now)
        with _restricted(engine, role) as db:
            assert service.authenticate(db, issued.token, now=now).subject == subject
            rotated = service.rotate(
                db,
                issued.token,
                csrf_token=issued.csrf_token,
                origin=ORIGIN,
                now=now,
            )
        with _restricted(engine, role) as db:
            with pytest.raises(SessionError, match="session_revoked"):
                service.authenticate(db, issued.token, now=now)
            service.revoke(db, rotated.token, csrf_token=rotated.csrf_token, origin=ORIGIN, now=now)
        with _restricted(engine, role) as db:
            with pytest.raises(SessionError, match="session_revoked"):
                service.authenticate(db, rotated.token, now=now)
    with Session(engine) as db:
        assert sorted(db.scalars(select(AuditRecord.action)).all()) == sorted(
            ["session_login", "session_rotate", "session_logout"] * 2
        )


def test_restricted_bff_denies_other_accounts_nonmembers_and_forbidden_operations(permissions):
    engine, role, now = permissions
    with _restricted(engine, role) as db:
        assert len(db.scalars(select(AccountMember)).all()) == 2
        assert db.get(AppSession, "f" * 64) is None
        for account, subject in ((ACCOUNT, SUBJECTS[2]), (OTHER_ACCOUNT, SUBJECTS[2])):
            with pytest.raises(SessionError, match="membership_unavailable"):
                SessionService(account, ORIGIN).issue(
                    db,
                    VerifiedIdentity(subject, now + timedelta(hours=1)),
                    now=now,
                )
    forbidden = [
        "SELECT * FROM accounts",
        "SELECT * FROM import_log",
        "SELECT * FROM source_records",
        "SELECT * FROM audit_log",
        "SELECT * FROM alembic_version",
        "UPDATE account_members SET revoked_at = NULL",
        "DELETE FROM account_members",
        "INSERT INTO account_members SELECT * FROM account_members",
        "DELETE FROM app_sessions",
        "UPDATE app_sessions SET expires_at = created_at",
        "UPDATE audit_log SET action = action",
        "DELETE FROM audit_log",
        "UPDATE source_records SET payload_json = payload_json",
        "DELETE FROM source_records",
        "INSERT INTO audit_log (id,occurred_at,actor,action,entity_type,entity_id,details_json) "
        f"VALUES ('forbidden','{now.isoformat()}','{SUBJECTS[0]}',"
        f"'not_session','account','{ACCOUNT}','{{}}')",
        "INSERT INTO app_sessions "
        "(token_hash,account_id,auth_subject,csrf_hash,created_at,expires_at) "
        f"VALUES ('{'c' * 64}','{OTHER_ACCOUNT}','{SUBJECTS[2]}','{'d' * 64}',"
        f"'{now.isoformat()}','{(now + timedelta(hours=1)).isoformat()}')",
    ]
    for statement in forbidden:
        with pytest.raises(DBAPIError) as caught, _restricted(engine, role) as db:
            db.execute(text(statement))
        assert caught.value.orig.args[0]["C"] == "42501"


def test_restricted_bff_rollback_removes_session_and_audit_together(permissions):
    engine, role, now = permissions
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        with _restricted(engine, role) as db:
            SessionService(ACCOUNT, ORIGIN).issue(
                db,
                VerifiedIdentity(SUBJECTS[0], now + timedelta(hours=1)),
                now=now,
            )
            raise RuntimeError("synthetic rollback")
    with Session(engine) as db:
        assert db.scalars(select(AppSession).where(AppSession.account_id == ACCOUNT)).all() == []
        assert db.scalars(select(AuditRecord)).all() == []
