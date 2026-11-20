"""Cash drill-down authorization commits before crossing the private binding."""

import asyncio

import httpx
from sqlalchemy.orm import Session
from test_session_http import KEY, Provider
from test_sessions import ACCOUNT, NOW, ORIGIN, SUBJECTS, issue
from test_sessions import engine as engine

from meridian.app import create_app
from meridian.security.http import SESSION_COOKIE, SessionHttp
from meridian.security.sessions import SessionService


def test_activity_http_requires_membership_origin_csrf_and_bounded_body(engine):
    sessions, calls = [], []

    def database():
        db = Session(engine)
        sessions.append(db)
        return db

    async def allowed():
        return True

    async def activity(value):
        assert all(not db.in_transaction() for db in sessions)
        calls.append(value)
        return {"entries": []}, 200

    handler = SessionHttp(
        SessionService(ACCOUNT, ORIGIN),
        Provider(),
        database,
        allowed,
        KEY,
        clock=lambda: NOW,
        cash_activity=activity,
    )
    query = dict(
        snapshot_id="saved-snapshot",
        input_revision="a" * 64,
        category="dividends",
        currency="GBP",
        offset=0,
        limit=20,
    )
    path = "/api/v1/portfolio/cash-activity"

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(session_http=handler)), base_url=ORIGIN
        ) as client:
            assert (
                await client.post(
                    path, json=query, headers={"origin": ORIGIN, "x-csrf-token": "a" * 43}
                )
            ).status_code == 401
            assert calls == []
            for subject in SUBJECTS:
                token = issue(engine, subject=subject)
                headers = {
                    "cookie": SESSION_COOKIE + "=" + token.token.get_secret_value(),
                    "origin": ORIGIN,
                    "x-csrf-token": token.csrf_token.get_secret_value(),
                }
                assert (
                    await client.post(
                        path, json=query, headers=headers | {"origin": "https://foreign.invalid"}
                    )
                ).status_code == 403
                assert (
                    await client.post(
                        path, json=query, headers=headers | {"x-csrf-token": "b" * 43}
                    )
                ).status_code == 403
                response = await client.post(path, json=query, headers=headers)
                assert (
                    response.status_code == 200 and response.headers["cache-control"] == "no-store"
                )
            assert len(calls) == 2
            assert (
                await client.post(
                    path, content="x" * 2049, headers=headers | {"content-type": "application/json"}
                )
            ).status_code == 400
            assert (
                await client.post(path, json=query | {"limit": True}, headers=headers)
            ).status_code == 400
            assert len(calls) == 2

    asyncio.run(run())
