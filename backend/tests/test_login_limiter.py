"""Durable login admission with synthetic local/CI databases; no hosted requests."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from test_persistence import engine as engine
from test_postgres import postgres_engine as postgres_engine
from test_postgres import postgres_schema as postgres_schema
from test_session_http import KEY, Provider, assert_private, login, scenario
from test_sessions import ACCOUNT, NOW, ORIGIN, seed

from meridian.app import create_app
from meridian.persistence.models import LoginRateLimit
from meridian.security.http import SESSION_COOKIE, SessionHttp
from meridian.security.login_limiter import DatabaseLoginLimiter, LoginLimiterError
from meridian.security.sessions import SessionService


class FixedClockLimiter(DatabaseLoginLimiter):
    epoch = 1000

    def _epoch(self, db):
        return self.epoch


def limiter(engine, bucket="synthetic-login", **kwargs):
    return FixedClockLimiter(lambda: Session(engine), bucket, **kwargs)


def stored(engine, bucket="synthetic-login"):
    with Session(engine) as db:
        record = db.get(LoginRateLimit, bucket)
        return None if record is None else (record.window_started_at, record.attempts)


def test_five_admissions_then_denial_persist_across_instances(engine):
    first = limiter(engine)
    assert [first.consume() for _ in range(5)] == [True] * 5
    assert first.consume() is False
    assert limiter(engine).consume() is False
    assert stored(engine) == (1000, 5)


def test_denial_does_not_slide_window_boundary_or_modify_count(engine):
    admission = limiter(engine, max_attempts=2, window_seconds=60)
    assert admission.consume() and admission.consume()
    admission.epoch = 1059
    assert admission.consume() is False
    assert stored(engine) == (1000, 2)
    admission.epoch = 1060
    assert admission.consume() is True
    assert stored(engine) == (1060, 1)
    admission.epoch = 1059
    assert admission.consume() is False
    assert stored(engine) == (1060, 1)
    admission.epoch = 1061
    assert admission.consume() is True
    assert admission.consume() is False
    assert stored(engine) == (1060, 2)


def test_clock_rollback_denied_even_before_saturation(engine):
    admission = limiter(engine)
    assert admission.consume()
    admission.epoch = 999
    assert admission.consume() is False
    assert stored(engine) == (1000, 1)


def test_distinct_buckets_have_independent_persisted_limits(engine):
    first = limiter(engine, "bucket-a", max_attempts=1)
    second = limiter(engine, "bucket-b", max_attempts=1)
    assert first.consume() and second.consume()
    assert first.consume() is False and second.consume() is False
    assert stored(engine, "bucket-a") == stored(engine, "bucket-b") == (1000, 1)


def test_database_clock_records_epoch_without_application_clock(engine):
    admission = DatabaseLoginLimiter(lambda: Session(engine), "database-time")
    earliest = int(time.time())
    assert admission.consume()
    latest = int(time.time())
    recorded, attempts = stored(engine, "database-time")
    assert earliest <= recorded <= latest
    assert attempts == 1


def test_async_callback_consumes_same_durable_bucket(engine):
    admission = limiter(engine, max_attempts=1)
    assert asyncio.run(admission()) is True
    assert asyncio.run(limiter(engine, max_attempts=1)()) is False
    assert stored(engine) == (1000, 1)


@pytest.mark.parametrize("bucket", [None, 12, "", "x" * 65, "bad space", "a/b", "é", "bucket\n"])
def test_invalid_bucket_is_rejected_without_echo(bucket):
    with pytest.raises(LoginLimiterError) as caught:
        DatabaseLoginLimiter(lambda: None, bucket)
    assert caught.value.code == "login_limiter_configuration_invalid"
    assert str(caught.value) == "login_limiter_configuration_invalid"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_attempts", 0),
        ("max_attempts", 1001),
        ("max_attempts", True),
        ("max_attempts", 1.0),
        ("window_seconds", 0),
        ("window_seconds", 3601),
        ("window_seconds", False),
        ("window_seconds", "60"),
    ],
)
def test_invalid_limit_configuration_is_closed(field, value):
    with pytest.raises(LoginLimiterError, match="login_limiter_configuration_invalid"):
        DatabaseLoginLimiter(lambda: None, "synthetic", **{field: value})


@pytest.mark.parametrize("epoch", [True, -1, "1000", 1000.0])
def test_invalid_database_epoch_fails_closed_without_row(engine, epoch):
    admission = limiter(engine)
    admission.epoch = epoch
    with pytest.raises(LoginLimiterError, match="login_limiter_unavailable"):
        admission.consume()
    assert stored(engine) is None


def test_connection_failure_is_redacted():
    def unavailable():
        raise ValueError("private-driver-password")

    with pytest.raises(LoginLimiterError) as caught:
        FixedClockLimiter(unavailable, "synthetic").consume()
    assert str(caught.value) == "login_limiter_unavailable"
    assert caught.value.__suppress_context__ is True
    assert "private" not in repr(caught.value)


def test_commit_failure_rolls_back_admission_and_preserves_prior_count(engine):
    assert limiter(engine).consume()

    def fail_commit(_session):
        raise ValueError("private-commit-password")

    def database():
        db = Session(engine)
        event.listen(db, "before_commit", fail_commit)
        return db

    with pytest.raises(LoginLimiterError, match="login_limiter_unavailable") as caught:
        FixedClockLimiter(database, "synthetic-login").consume()
    assert "private" not in repr(caught.value)
    assert stored(engine) == (1000, 1)
    assert limiter(engine).consume()
    assert stored(engine) == (1000, 2)


def test_http_login_uses_persisted_admission_and_maps_storage_failure_503(engine):
    seed(engine)
    provider = Provider()

    def application(callback):
        handler = SessionHttp(
            SessionService(ACCOUNT, ORIGIN),
            provider,
            lambda: Session(engine),
            callback,
            KEY,
            clock=lambda: NOW,
        )
        return create_app(session_http=handler)

    async def accepted(client):
        response = await login(client)
        assert response.status_code == 200
        assert_private(response)

    async def denied(client):
        response = await login(client)
        assert response.status_code == 429
        assert_private(response)
        assert SESSION_COOKIE not in response.cookies

    scenario(application(limiter(engine, max_attempts=1)), accepted)
    scenario(application(limiter(engine, max_attempts=1)), denied)
    assert provider.calls == 1

    def unavailable():
        raise ValueError("private-limiter-database")

    async def failed(client):
        response = await login(client)
        assert response.status_code == 503
        assert_private(response)
        assert SESSION_COOKIE not in response.cookies

    scenario(application(FixedClockLimiter(unavailable, "synthetic-failure")), failed)
    assert provider.calls == 1


@pytest.mark.postgres
def test_postgres_parallel_admissions_never_exceed_shared_budget(postgres_engine):
    barrier = Barrier(12)

    def consume(_index):
        admission = limiter(postgres_engine, max_attempts=5)
        barrier.wait(timeout=20)
        return admission.consume()

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(consume, range(12)))
    assert outcomes.count(True) == 5
    assert outcomes.count(False) == 7
    assert stored(postgres_engine) == (1000, 5)
    with Session(postgres_engine) as db:
        assert len(db.scalars(select(LoginRateLimit)).all()) == 1


@pytest.mark.postgres
def test_postgres_uses_real_database_epoch_without_application_clock(postgres_engine):
    with postgres_engine.connect() as connection:
        before = connection.scalar(text("SELECT floor(extract(epoch FROM clock_timestamp()))"))
    admission = DatabaseLoginLimiter(lambda: Session(postgres_engine), "postgres-clock")
    assert admission.consume() is True
    with postgres_engine.connect() as connection:
        after = connection.scalar(text("SELECT floor(extract(epoch FROM clock_timestamp()))"))
    epoch, attempts = stored(postgres_engine, "postgres-clock")
    assert type(epoch) is int and before <= epoch <= after
    assert attempts == 1


@pytest.mark.postgres
def test_postgres_locked_bucket_fails_closed_without_increment(postgres_engine):
    admission = limiter(postgres_engine)
    assert admission.consume() is True
    with ThreadPoolExecutor(max_workers=1) as pool:
        with postgres_engine.begin() as connection:
            connection.execute(select(LoginRateLimit).with_for_update()).all()
            waiting = pool.submit(admission.consume)
            with pytest.raises(LoginLimiterError, match="login_limiter_unavailable"):
                waiting.result(timeout=12)
    assert stored(postgres_engine) == (1000, 1)
    assert admission.consume() is True
    assert stored(postgres_engine) == (1000, 2)


def test_provider_rejection_does_not_refund_committed_admission(engine):
    from meridian.security.supabase_auth import AuthError

    seed(engine)
    provider = Provider(failure=AuthError("auth_rejected"))
    handler = SessionHttp(
        SessionService(ACCOUNT, ORIGIN),
        provider,
        lambda: Session(engine),
        limiter(engine, max_attempts=1),
        KEY,
        clock=lambda: NOW,
    )
    app = create_app(session_http=handler)

    async def check(client):
        rejected = await login(client)
        assert rejected.status_code == 401
        assert_private(rejected)
        throttled = await login(client)
        assert throttled.status_code == 429
        assert_private(throttled)

    scenario(app, check)
    assert provider.calls == 1
    assert stored(engine) == (1000, 1)
