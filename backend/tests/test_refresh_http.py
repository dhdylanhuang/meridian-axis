"""Both approved members share refresh authority with existing session/CSRF checks."""

import asyncio
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session
from test_session_http import KEY, Provider
from test_sessions import NOW, ORIGIN, SUBJECTS
from test_sessions import engine as engine
from test_snapshot_access import seed

from meridian.app import create_app
from meridian.persistence.models import AccountMember
from meridian.security.http import SESSION_COOKIE, SessionHttp
from meridian.security.sessions import SessionService
from meridian.security.supabase_auth import VerifiedIdentity


def test_manual_refresh_requires_session_origin_csrf_and_committed_authorization(engine):
    seed(engine)
    service = SessionService("shared-isa", ORIGIN)
    issued, sessions, called = [], [], []
    with Session(engine) as db, db.begin():
        for slot, subject in enumerate(SUBJECTS, 1):
            db.add(
                AccountMember(
                    account_id="shared-isa", auth_subject=subject, slot=slot, created_at=NOW
                )
            )
        db.flush()
        for subject in SUBJECTS:
            issued.append(
                service.issue(db, VerifiedIdentity(subject, NOW + timedelta(hours=1)), now=NOW)
            )

    def database():
        db = Session(engine)
        sessions.append(db)
        return db

    async def allowed():
        return True

    async def refresh():
        assert all(not db.in_transaction() for db in sessions)
        called.append(True)
        return {"status": "succeeded"}

    handler = SessionHttp(
        service, Provider(), database, allowed, KEY, clock=lambda: NOW, refresh=refresh
    )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(session_http=handler)), base_url=ORIGIN
        ) as client:
            path = "/api/v1/portfolio/refresh"
            assert (
                await client.post(path, headers={"origin": ORIGIN, "x-csrf-token": "a" * 43})
            ).status_code == 401
            assert (await client.get(path + "/status")).status_code == 401
            for user in issued:
                headers = {
                    "cookie": SESSION_COOKIE + "=" + user.token.get_secret_value(),
                    "origin": ORIGIN,
                    "x-csrf-token": user.csrf_token.get_secret_value(),
                }
                response = await client.post(path, headers=headers)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
                assert (
                    await client.post(path, headers=headers | {"x-csrf-token": "b" * 43})
                ).status_code == 403
                assert (
                    await client.post(path, headers=headers | {"origin": "https://other.invalid"})
                ).status_code == 403
                health = await client.get(path + "/status", headers={"cookie": headers["cookie"]})
                assert health.status_code == 200 and health.json()["quote_age"] == "unknown"
            assert len(called) == 2
            with Session(engine) as db, db.begin():
                db.get(AccountMember, ("shared-isa", SUBJECTS[0])).revoked_at = NOW
            assert (
                await client.post(
                    path,
                    headers={
                        "cookie": SESSION_COOKIE + "=" + issued[0].token.get_secret_value(),
                        "origin": ORIGIN,
                        "x-csrf-token": issued[0].csrf_token.get_secret_value(),
                    },
                )
            ).status_code == 401
            assert len(called) == 2

    asyncio.run(run())
