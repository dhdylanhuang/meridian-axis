"""Real factory wiring, lazy connection and resource ownership; no remote calls."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.pool import NullPool

from meridian.security import hosted

ORIGIN = "https://synthetic.invalid"


def binding(**overrides):
    return SimpleNamespace(
        **dict(
            user="meridian_bff_public",
            password="invented-binding-password",
            host="hyperdrive-local.invalid",
            port=5432,
            database="postgres",
        )
        | overrides
    )


def configuration():
    return dict(
        origin=ORIGIN,
        project_ref="a" * 20,
        publishable_key=SecretStr("sb_publishable_invented"),
        login_csrf_key=SecretStr("invented-signing-key-at-least-32-bytes"),
    )


def test_factory_bootstrap_and_anonymous_denial_without_connecting(monkeypatch):
    connect = Mock(side_effect=AssertionError("Unexpected database connection"))
    monkeypatch.setattr(hosted.pg8000.dbapi, "connect", connect)

    async def run():
        async with hosted.hosted_application(binding(), **configuration()) as app:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url=ORIGIN
            ) as client:
                health = await client.get("/health")
                assert health.status_code == 200 and health.json() == {"status": "ok"}
                boot = await client.get("/api/v1/session/bootstrap")
                assert boot.status_code == 200
                assert len(boot.json()["csrf_token"]) == 43
                assert "HttpOnly" in boot.headers["set-cookie"]
                assert (await client.get("/api/v1/session/current")).status_code == 401
                assert (await client.get("/openapi.json")).status_code == 404
                foreign = await client.get(
                    "/api/v1/session/bootstrap", headers={"Origin": "https://other.invalid"}
                )
                assert foreign.status_code == 403
        connect.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize(
    "overrides",
    [{"user": "postgres"}, {"database": "other"}, {"port": 0}, {"password": ""}],
)
def test_bad_binding_fails_before_creating_engine(monkeypatch, overrides):
    create = Mock(side_effect=AssertionError("Engine must not be created"))
    monkeypatch.setattr(hosted, "create_engine", create)

    async def run():
        with pytest.raises(ValueError):
            async with hosted.hosted_application(binding(**overrides), **configuration()):
                pytest.fail("Invalid configuration yielded")
        create.assert_not_called()

    asyncio.run(run())


def test_disposal_on_request_failure_and_secret_free_engine_url(monkeypatch):
    original = hosted.create_engine
    engines = []

    def track(*args, **kwargs):
        assert args == ("postgresql+pg8000://",)
        assert kwargs["poolclass"] is NullPool
        assert kwargs["hide_parameters"] is True
        engine = original(*args, **kwargs)
        engine.dispose = Mock(wraps=engine.dispose)
        engines.append(engine)
        return engine

    monkeypatch.setattr(hosted, "create_engine", track)

    async def run():
        with pytest.raises(RuntimeError, match="invented_failure"):
            async with hosted.hosted_application(binding(), **configuration()):
                raise RuntimeError("invented_failure")
        engines[0].dispose.assert_called_once_with()
        assert "invented-binding-password" not in str(engines[0].url)

    asyncio.run(run())


def test_wired_provider_limiter_session_lifecycle(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from meridian.persistence.database import create_db_engine, upgrade_database
    from meridian.persistence.models import Account, AccountMember, AppSession, LoginRateLimit
    from meridian.security.http import CSRF_COOKIE, SESSION_COOKIE

    path = tmp_path / "wired.sqlite3"
    upgrade_database(path)
    engine = create_db_engine(path)
    now = datetime.now(UTC)
    subject = "11111111-1111-4111-8111-111111111111"
    with Session(engine) as db, db.begin():
        db.add(Account(id="shared-isa", environment="demo"))
        db.flush()
        db.add(AccountMember(account_id="shared-isa", auth_subject=subject, slot=1, created_at=now))
    actual_client = httpx.AsyncClient
    provider_calls = []

    def provider(request):
        provider_calls.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "access_token": "invented-provider-access-token",
                    "token_type": "bearer",
                    "expires_at": int((now + timedelta(minutes=10)).timestamp()),
                    "expires_in": 600,
                    "user": {"id": subject},
                },
            )
        assert request.headers["authorization"] == "Bearer invented-provider-access-token"
        return httpx.Response(200, json={"id": subject})

    monkeypatch.setattr(hosted, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        hosted.httpx, "AsyncClient", lambda: actual_client(transport=httpx.MockTransport(provider))
    )

    async def run():
        async with hosted.hosted_application(binding(), **configuration()) as app:
            async with actual_client(
                transport=httpx.ASGITransport(app=app), base_url=ORIGIN
            ) as client:
                bootstrap = await client.get("/api/v1/session/bootstrap")
                response = await client.post(
                    "/api/v1/session/login",
                    headers={"origin": ORIGIN, "x-csrf-token": bootstrap.json()["csrf_token"]},
                    json={"email": "synthetic@example.invalid", "password": "invented-password"},
                )
                assert response.status_code == 200, response.text
                assert "invented-provider-access-token" not in response.text
                old_token = client.cookies[SESSION_COOKIE]
                current = await client.get("/api/v1/session/current")
                assert current.status_code == 200 and current.json()["subject"] == subject
                rotated = await client.post(
                    "/api/v1/session/rotate",
                    headers={"origin": ORIGIN, "x-csrf-token": client.cookies[CSRF_COOKIE]},
                )
                assert rotated.status_code == 200
                assert client.cookies[SESSION_COOKIE] != old_token
                logout = await client.post(
                    "/api/v1/session/logout",
                    headers={"origin": ORIGIN, "x-csrf-token": client.cookies[CSRF_COOKIE]},
                )
                assert logout.status_code == 200
                assert (await client.get("/api/v1/session/current")).status_code == 401
        with Session(engine) as db:
            assert db.get(LoginRateLimit, "shared-login").attempts == 1
            assert all(row.revoked_at is not None for row in db.scalars(select(AppSession)))
        assert provider_calls == ["/auth/v1/token", "/auth/v1/user"]

    asyncio.run(run())
