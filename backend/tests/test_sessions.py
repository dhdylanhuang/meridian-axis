"""Synthetic session lifecycle, membership, CSRF and atomicity checks."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema

from meridian.persistence.database import create_db_engine, upgrade_database
from meridian.persistence.models import Account, AccountMember, AppSession, AuditRecord
from meridian.security.sessions import SessionError, SessionService
from meridian.security.supabase_auth import VerifiedIdentity

NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)
ORIGIN = "https://synthetic.example"
SUBJECTS = ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222")
ACCOUNT = "synthetic-session-account"


def seed(engine):
    with Session(engine) as db, db.begin():
        db.add(Account(id=ACCOUNT, environment="demo"))
        db.flush()
        for slot, subject in enumerate(SUBJECTS, 1):
            db.add(
                AccountMember(
                    account_id=ACCOUNT,
                    auth_subject=subject,
                    slot=slot,
                    created_at=NOW,
                )
            )


@pytest.fixture
def engine(tmp_path):
    path = tmp_path / "sessions.sqlite3"
    upgrade_database(path)
    engine = create_db_engine(path)
    seed(engine)
    yield engine
    engine.dispose()


def issue(engine, subject=SUBJECTS[0], expiry=NOW + timedelta(hours=2)):
    with Session(engine) as db, db.begin():
        return SessionService(ACCOUNT, ORIGIN).issue(
            db,
            VerifiedIdentity(subject, expiry),
            now=NOW,
        )


def mutation(issued):
    return {"csrf_token": issued.csrf_token, "origin": ORIGIN, "now": NOW + timedelta(seconds=1)}


def test_both_members_have_identical_rights_and_only_hashes_are_stored(engine):
    issued = [issue(engine, subject) for subject in SUBJECTS]
    assert issued[0].token != issued[1].token
    service = SessionService(ACCOUNT, ORIGIN)
    with Session(engine) as db:
        for subject, credentials in zip(SUBJECTS, issued, strict=True):
            principal = service.authorize_mutation(db, credentials.token, **mutation(credentials))
            assert (principal.account_id, principal.subject) == (ACCOUNT, subject)
            assert credentials.expires_at == NOW + timedelta(hours=1)
            row = db.get(
                AppSession,
                hashlib.sha256(credentials.token.get_secret_value().encode("ascii")).hexdigest(),
            )
            assert row is not None
            assert (
                row.csrf_hash
                == hashlib.sha256(
                    credentials.csrf_token.get_secret_value().encode("ascii")
                ).hexdigest()
            )
            audit = repr(
                [
                    (a.action, a.actor, a.entity_id, a.details_json)
                    for a in db.scalars(select(AuditRecord))
                ]
            )
            for secret in (credentials.token, credentials.csrf_token):
                assert secret.get_secret_value() not in repr(credentials)
                assert secret.get_secret_value() not in audit
            assert row.token_hash not in audit and row.csrf_hash not in audit


def test_provider_expiry_bounds_session_and_nonmember_is_denied(engine):
    expiry = NOW + timedelta(minutes=5)
    issued = issue(engine, expiry=expiry)
    assert issued.expires_at == expiry
    with Session(engine) as db, db.begin():
        for identity, code in (
            (VerifiedIdentity(SUBJECTS[0], NOW), "provider_identity_expired"),
            (
                VerifiedIdentity("33333333-3333-4333-8333-333333333333", expiry),
                "membership_unavailable",
            ),
        ):
            with pytest.raises(SessionError, match=code):
                SessionService(ACCOUNT, ORIGIN).issue(db, identity, now=NOW)


@pytest.mark.parametrize("token", [None, "", "private-invalid-token", "☃" * 43, "x" * 44])
def test_missing_or_malformed_tokens_are_safe(engine, token):
    with Session(engine) as db, pytest.raises(SessionError, match="session_invalid") as error:
        SessionService(ACCOUNT, ORIGIN).authenticate(db, token, now=NOW)
    assert "private" not in str(error.value)


def test_expiry_and_account_boundary(engine):
    credentials = issue(engine)
    with Session(engine) as db:
        with pytest.raises(SessionError, match="session_expired"):
            SessionService(ACCOUNT, ORIGIN).authenticate(
                db, credentials.token, now=credentials.expires_at
            )
        with pytest.raises(SessionError, match="session_invalid"):
            SessionService("other-synthetic-account", ORIGIN).authenticate(
                db, credentials.token, now=NOW
            )


def test_revocation_refreshes_cached_membership(engine):
    credentials = issue(engine)
    service = SessionService(ACCOUNT, ORIGIN)
    with Session(engine, expire_on_commit=False) as cached:
        service.authenticate(cached, credentials.token, now=NOW)
        cached.commit()
        with Session(engine) as writer, writer.begin():
            writer.get(AccountMember, (ACCOUNT, SUBJECTS[0])).revoked_at = NOW
        with pytest.raises(SessionError, match="membership_unavailable"):
            service.authenticate(cached, credentials.token, now=NOW)


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "http://synthetic.example",
        "https://synthetic.example/",
        "https://evil.example",
    ],
)
def test_mutations_require_exact_origin(engine, origin):
    credentials = issue(engine)
    with Session(engine) as db, pytest.raises(SessionError, match="origin_invalid"):
        SessionService(ACCOUNT, ORIGIN).revoke(
            db, credentials.token, csrf_token=credentials.csrf_token, origin=origin, now=NOW
        )


@pytest.mark.parametrize("csrf", [None, "wrong", "x" * 43])
def test_mutations_require_bound_csrf(engine, csrf):
    credentials = issue(engine)
    with Session(engine) as db, pytest.raises(SessionError, match="csrf_invalid"):
        SessionService(ACCOUNT, ORIGIN).revoke(
            db, credentials.token, csrf_token=csrf, origin=ORIGIN, now=NOW
        )


def test_rotation_consumes_old_session_and_logout_revokes_successor(engine):
    credentials = issue(engine)
    service = SessionService(ACCOUNT, ORIGIN)
    with Session(engine) as db, db.begin():
        rotated = service.rotate(db, credentials.token, **mutation(credentials))
    assert rotated.token != credentials.token and rotated.csrf_token != credentials.csrf_token
    assert rotated.expires_at == credentials.expires_at
    with Session(engine) as db, db.begin():
        with pytest.raises(SessionError, match="session_revoked"):
            service.authenticate(db, credentials.token, now=NOW + timedelta(seconds=2))
        service.revoke(db, rotated.token, **mutation(rotated))
    with Session(engine) as db, pytest.raises(SessionError, match="session_revoked"):
        service.authenticate(db, rotated.token, now=NOW + timedelta(seconds=2))


def test_rotation_rollback_restores_prior_session_and_audit(engine):
    credentials = issue(engine)
    service = SessionService(ACCOUNT, ORIGIN)
    with pytest.raises(RuntimeError, match="synthetic_abort"):
        with Session(engine) as db, db.begin():
            successor = service.rotate(db, credentials.token, **mutation(credentials))
            raise RuntimeError("synthetic_abort")
    with Session(engine) as db:
        assert service.authenticate(db, credentials.token, now=NOW).subject == SUBJECTS[0]
        with pytest.raises(SessionError, match="session_invalid"):
            service.authenticate(db, successor.token, now=NOW)
        assert len(db.scalars(select(AuditRecord)).all()) == 1


def test_audit_failure_does_not_commit_login(engine):
    def fail(*_args):
        raise RuntimeError("synthetic_audit_failure")

    event.listen(AuditRecord, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic_audit_failure"):
            issue(engine)
    finally:
        event.remove(AuditRecord, "before_insert", fail)
    with Session(engine) as db:
        assert db.scalars(select(AppSession)).all() == []
        assert db.scalars(select(AuditRecord)).all() == []


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8000",
        "https://user:password@example.invalid",
        "https://example.invalid/path",
        "https://example.invalid?key=private",
    ],
)
def test_origin_configuration_is_closed(origin):
    with pytest.raises(SessionError, match="session_configuration_invalid"):
        SessionService(ACCOUNT, origin)


@pytest.mark.postgres
def test_concurrent_rotations_have_only_one_successor(postgres_engine):
    seed(postgres_engine)
    credentials = issue(postgres_engine)
    barrier = Barrier(2)

    class RacingService(SessionService):
        def _mutation(self, *args):
            record = super()._mutation(*args)
            barrier.wait(timeout=10)
            return record

    service = RacingService(ACCOUNT, ORIGIN)

    def rotate():
        try:
            with Session(postgres_engine) as db, db.begin():
                service.rotate(db, credentials.token, **mutation(credentials))
            return "ok"
        except SessionError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: rotate(), range(2))) == ["ok", "session_revoked"]
    with Session(postgres_engine) as db:
        assert len(db.scalars(select(AppSession)).all()) == 2
        assert len(db.scalars(select(AppSession).where(AppSession.revoked_at.is_(None))).all()) == 1
        assert (
            len(db.scalars(select(AuditRecord).where(AuditRecord.action == "session_rotate")).all())
            == 1
        )
