"""Offline HTTPS ASGI session transport tests; cookie attributes only, no browser claims."""

import asyncio
from datetime import timedelta
from http.cookies import SimpleCookie

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_sessions import ACCOUNT, NOW, ORIGIN, SUBJECTS
from test_sessions import engine as engine

from meridian.app import create_app
from meridian.persistence.models import AppSession, AuditRecord
from meridian.security.http import CSRF_COOKIE, LOGIN_COOKIE, PREFIX, SESSION_COOKIE, SessionHttp
from meridian.security.sessions import SessionService
from meridian.security.supabase_auth import AuthError, VerifiedIdentity

PASSWORD = "invented-private-password"
KEY = SecretStr("invented-signing-key-only-for-tests-32bytes")


class Provider:
    def __init__(self, subject=SUBJECTS[0], failure=None):
        self.subject, self.failure = subject, failure
        self.calls = 0

    async def sign_in(self, email, password):
        self.calls += 1
        assert email == "synthetic@example.invalid"
        assert isinstance(password, SecretStr) and password.get_secret_value() == PASSWORD
        if self.failure:
            raise self.failure
        return VerifiedIdentity(self.subject, NOW + timedelta(minutes=5))


def configured(engine, *, provider=None, permitted=True, clock=lambda: NOW):
    provider = provider or Provider()

    async def limiter():
        if isinstance(permitted, Exception):
            raise permitted
        return permitted

    handler = SessionHttp(
        SessionService(ACCOUNT, ORIGIN),
        provider,
        lambda: Session(engine),
        limiter,
        KEY,
        clock=clock,
    )
    return create_app(session_http=handler), provider


def scenario(app, operation, *, base_url=ORIGIN):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url, follow_redirects=False
        ) as client:
            return await operation(client)

    return asyncio.run(run())


async def bootstrap(client):
    response = await client.get(PREFIX + "/bootstrap")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()["csrf_token"]


async def login(client):
    nonce = await bootstrap(client)
    return await client.post(
        PREFIX + "/login",
        headers={"origin": ORIGIN, "x-csrf-token": nonce},
        json={"email": "synthetic@example.invalid", "password": PASSWORD},
    )


def cookies(response):
    parsed = SimpleCookie()
    for value in response.headers.get_list("set-cookie"):
        parsed.load(value)
    return parsed


def assert_private(response):
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "access-control-allow-origin" not in response.headers
    assert PASSWORD not in response.text
    assert KEY.get_secret_value() not in response.text
    assert "access_token" not in response.text and "refresh_token" not in response.text


@pytest.mark.parametrize("subject", SUBJECTS)
def test_both_members_login_current_rotate_logout_with_private_cookies(engine, subject):
    app, provider = configured(engine, provider=Provider(subject))

    async def check(client):
        response = await login(client)
        assert response.status_code == 200
        assert set(response.json()) == {"expires_at"}
        assert_private(response)
        issued = cookies(response)
        for name in (SESSION_COOKIE, CSRF_COOKIE):
            cookie = issued[name]
            assert cookie["secure"] and cookie["samesite"] == "strict" and cookie["path"] == "/"
            assert not cookie["domain"]
            assert cookie["max-age"] == "300" and cookie["expires"]
            assert bool(cookie["httponly"]) is (name == SESSION_COOKIE)
            assert cookie.value not in response.text
        assert issued[LOGIN_COOKIE]["max-age"] == "0"
        old_token, old_csrf = client.cookies[SESSION_COOKIE], client.cookies[CSRF_COOKIE]
        current = await client.get(PREFIX + "/current")
        assert current.status_code == 200
        assert current.json() == {"subject": subject, "expires_at": response.json()["expires_at"]}
        assert_private(current)
        rotated = await client.post(
            PREFIX + "/rotate", headers={"origin": ORIGIN, "x-csrf-token": old_csrf}
        )
        assert rotated.status_code == 200
        assert rotated.json()["expires_at"] == response.json()["expires_at"]
        assert (
            client.cookies[SESSION_COOKIE] != old_token and client.cookies[CSRF_COOKIE] != old_csrf
        )
        rejected = await client.get(
            PREFIX + "/current", headers={"cookie": SESSION_COOKIE + "=" + old_token}
        )
        assert rejected.status_code == 401
        logout = await client.post(
            PREFIX + "/logout",
            headers={"origin": ORIGIN, "x-csrf-token": client.cookies[CSRF_COOKIE]},
        )
        assert logout.status_code == 200
        assert_private(logout)
        assert all(
            cookies(logout)[name]["max-age"] == "0"
            for name in (SESSION_COOKIE, CSRF_COOKIE, LOGIN_COOKIE)
        )
        assert (await client.get(PREFIX + "/current")).status_code == 401

    scenario(app, check)
    assert provider.calls == 1
    with Session(engine) as db:
        assert len(db.scalars(select(AuditRecord)).all()) == 3


def test_bootstrap_sets_signed_httponly_prelogin_cookie(engine):
    app, _ = configured(engine)

    async def check(client):
        response = await client.get(PREFIX + "/bootstrap")
        cookie = cookies(response)[LOGIN_COOKIE]
        assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "strict"
        assert cookie["path"] == "/" and not cookie["domain"] and cookie["max-age"] == "300"
        assert len(cookie.value.split(".")) == 3
        assert response.json()["csrf_token"] == cookie.value.split(".")[0]
        assert cookie.value not in response.text
        assert_private(response)

    scenario(app, check)


@pytest.mark.parametrize("origin", [None, "null", "https://foreign.invalid", ORIGIN + "/"])
def test_login_requires_exact_origin_before_provider(engine, origin):
    app, provider = configured(engine)

    async def check(client):
        nonce = await bootstrap(client)
        headers = {"x-csrf-token": nonce}
        if origin is not None:
            headers["origin"] = origin
        response = await client.post(
            PREFIX + "/login",
            headers=headers,
            json={"email": "synthetic@example.invalid", "password": PASSWORD},
        )
        assert response.status_code == 403
        assert_private(response)

    scenario(app, check)
    assert provider.calls == 0


@pytest.mark.parametrize("kind", ["missing", "wrong", "tampered", "expired", "future"])
def test_prelogin_nonce_failure_never_calls_provider(engine, kind):
    clock = [NOW]
    app, provider = configured(engine, clock=lambda: clock[0])

    async def check(client):
        nonce = await bootstrap(client)
        headers = {"origin": ORIGIN, "x-csrf-token": nonce}
        if kind == "missing":
            client.cookies.clear()
        elif kind == "wrong":
            headers["x-csrf-token"] = "x" * 43
        elif kind == "tampered":
            value = client.cookies[LOGIN_COOKIE]
            headers["cookie"] = LOGIN_COOKIE + "=" + value[:-1] + ("0" if value[-1] != "0" else "1")
        else:
            clock[0] += timedelta(seconds=301 if kind == "expired" else -1)
        response = await client.post(
            PREFIX + "/login",
            headers=headers,
            json={"email": "synthetic@example.invalid", "password": PASSWORD},
        )
        assert response.status_code == 403
        assert_private(response)

    scenario(app, check)
    assert provider.calls == 0


@pytest.mark.parametrize(
    "body,content_type",
    [
        (
            '{"email":"synthetic@example.invalid","password":"'
            + PASSWORD
            + '","password":"other"}',
            "application/json",
        ),
        (
            '{"email":"synthetic@example.invalid","password":"' + PASSWORD + '","extra":true}',
            "application/json",
        ),
        ('{"email":"synthetic@example.invalid","password":12}', "application/json"),
        ("[]", "application/json"),
        (PASSWORD, "application/json"),
        ('{"email":"synthetic@example.invalid","password":"' + PASSWORD + '"}', "text/plain"),
        (" " * 8193, "application/json"),
    ],
)
def test_invalid_login_body_is_bounded_redacted_and_not_422(engine, body, content_type):
    app, provider = configured(engine)

    async def check(client):
        nonce = await bootstrap(client)
        response = await client.post(
            PREFIX + "/login",
            headers={"origin": ORIGIN, "x-csrf-token": nonce, "content-type": content_type},
            content=body,
        )
        assert response.status_code == 400
        assert_private(response)

    scenario(app, check)
    assert provider.calls == 0


@pytest.mark.parametrize(
    "permitted,status", [(False, 429), (1, 429), (RuntimeError(PASSWORD), 503)]
)
def test_shared_limiter_denial_or_failure_prevents_provider(engine, permitted, status):
    app, provider = configured(engine, permitted=permitted)

    async def check(client):
        response = await login(client)
        assert response.status_code == status
        assert_private(response)
        assert SESSION_COOKIE not in cookies(response)

    scenario(app, check)
    assert provider.calls == 0


@pytest.mark.parametrize(
    "failure,status", [(AuthError("auth_rejected"), 401), (RuntimeError(PASSWORD), 503)]
)
def test_provider_failure_issues_no_session_or_audit(engine, failure, status):
    app, _ = configured(engine, provider=Provider(failure=failure))

    async def check(client):
        response = await login(client)
        assert response.status_code == status
        assert_private(response)
        assert SESSION_COOKIE not in cookies(response)

    scenario(app, check)
    with Session(engine) as db:
        assert db.scalars(select(AppSession)).all() == []
        assert db.scalars(select(AuditRecord)).all() == []


def test_database_audit_failure_rolls_back_login_without_credentials_response(engine):
    app, _ = configured(engine)

    def fail(*_args):
        raise RuntimeError(PASSWORD)

    event.listen(AuditRecord, "before_insert", fail)
    try:

        async def check(client):
            response = await login(client)
            assert response.status_code == 503
            assert_private(response)
            assert SESSION_COOKIE not in cookies(response)

        scenario(app, check)
    finally:
        event.remove(AuditRecord, "before_insert", fail)
    with Session(engine) as db:
        assert db.scalars(select(AppSession)).all() == []
        assert db.scalars(select(AuditRecord)).all() == []


@pytest.mark.parametrize("kind", ["origin", "csrf_header", "session_cookie", "login_cookie"])
def test_duplicate_security_headers_and_cookies_are_rejected(engine, kind):
    app, _ = configured(engine)

    async def check(client):
        if kind == "login_cookie":
            nonce = await bootstrap(client)
            value = client.cookies[LOGIN_COOKIE]
            response = await client.post(
                PREFIX + "/login",
                headers=[
                    ("origin", ORIGIN),
                    ("x-csrf-token", nonce),
                    ("cookie", f"{LOGIN_COOKIE}={value}; {LOGIN_COOKIE}={value}"),
                ],
                json={"email": "synthetic@example.invalid", "password": PASSWORD},
            )
            assert response.status_code == 403
            return
        assert (await login(client)).status_code == 200
        headers = [("origin", ORIGIN), ("x-csrf-token", client.cookies[CSRF_COOKIE])]
        if kind == "origin":
            headers.append(("origin", ORIGIN))
        elif kind == "csrf_header":
            headers.append(("x-csrf-token", client.cookies[CSRF_COOKIE]))
        else:
            value = client.cookies[SESSION_COOKIE]
            headers.append(("cookie", f"{SESSION_COOKIE}={value}; {SESSION_COOKIE}={value}"))
        response = await client.post(PREFIX + "/rotate", headers=headers)
        assert response.status_code in (401, 403)
        assert_private(response)

    scenario(app, check)


@pytest.mark.parametrize("failure", ["origin", "csrf", "no_csrf"])
def test_rotation_and_logout_require_origin_and_bound_csrf(engine, failure):
    app, _ = configured(engine)

    async def check(client):
        assert (await login(client)).status_code == 200
        headers = {"origin": ORIGIN, "x-csrf-token": client.cookies[CSRF_COOKIE]}
        if failure == "origin":
            headers["origin"] = "https://foreign.invalid"
        elif failure == "csrf":
            headers["x-csrf-token"] = "x" * 43
        else:
            del headers["x-csrf-token"]
        for path in ("/rotate", "/logout"):
            response = await client.post(PREFIX + path, headers=headers)
            assert response.status_code == 403
            assert_private(response)
        assert (await client.get(PREFIX + "/current")).status_code == 200

    scenario(app, check)


@pytest.mark.parametrize(
    "base,headers,path",
    [
        ("http://synthetic.example", {}, "/bootstrap"),
        ("https://wrong.invalid", {}, "/bootstrap"),
        (ORIGIN, {"origin": "https://foreign.invalid"}, "/bootstrap"),
        (ORIGIN, {"origin": "https://foreign.invalid"}, "/current"),
        (ORIGIN, {"host": "wrong.invalid"}, "/bootstrap"),
        (ORIGIN, {}, "/bootstrap?secret=private"),
    ],
)
def test_https_authority_foreign_read_origin_and_query_boundaries(engine, base, headers, path):
    app, _ = configured(engine)

    async def check(client):
        response = await client.get(PREFIX + path, headers=headers)
        assert response.status_code == 403
        assert_private(response)

    scenario(app, check, base_url=base)


def test_duplicate_host_is_rejected(engine):
    app, _ = configured(engine)

    async def check(client):
        response = await client.get(
            PREFIX + "/bootstrap",
            headers=[("host", "synthetic.example"), ("host", "synthetic.example")],
        )
        assert response.status_code == 403

    scenario(app, check)


@pytest.mark.parametrize("enabled", [False, True])
def test_disabled_by_default_and_framework_errors_are_private(engine, enabled):
    app = configured(engine)[0] if enabled else create_app()

    async def check(client):
        for method, path, expected in (
            ("GET", "/current", 401 if enabled else 404),
            ("GET", "/unknown", 404),
            ("GET", "/login", 405 if enabled else 404),
            ("GET", "/bootstrap/", 404),
        ):
            response = await client.request(method, PREFIX + path)
            assert response.status_code == expected
            assert_private(response)

    scenario(app, check)


def test_router_requires_signing_key_and_callable_shared_limiter(engine):
    service = SessionService(ACCOUNT, ORIGIN)
    for limiter, key in ((None, KEY), (lambda: True, SecretStr("short"))):
        with pytest.raises(ValueError, match="session_http_configuration_invalid"):
            SessionHttp(service, Provider(), lambda: Session(engine), limiter, key)


def test_commit_failure_rolls_back_login_and_audit_before_setting_cookies(engine):
    def fail_commit(_session):
        raise RuntimeError(PASSWORD)

    def database():
        session = Session(engine)
        event.listen(session, "before_commit", fail_commit)
        return session

    async def limiter():
        return True

    handler = SessionHttp(
        SessionService(ACCOUNT, ORIGIN), Provider(), database, limiter, KEY, clock=lambda: NOW
    )
    app = create_app(session_http=handler)

    async def check(client):
        response = await login(client)
        assert response.status_code == 503
        assert_private(response)
        assert SESSION_COOKIE not in cookies(response)
        assert CSRF_COOKIE not in cookies(response)

    scenario(app, check)
    with Session(engine) as db:
        assert db.scalars(select(AppSession)).all() == []
        assert db.scalars(select(AuditRecord)).all() == []


def test_nonmember_login_is_denied_without_session_or_cookie(engine):
    app, _ = configured(engine, provider=Provider("33333333-3333-4333-8333-333333333333"))

    async def check(client):
        response = await login(client)
        assert response.status_code == 401
        assert_private(response)
        assert SESSION_COOKIE not in cookies(response)

    scenario(app, check)
    with Session(engine) as db:
        assert db.scalars(select(AppSession)).all() == []
        assert db.scalars(select(AuditRecord)).all() == []


@pytest.mark.parametrize("state", ["expired", "revoked_member"])
def test_current_denies_expired_session_or_revoked_membership(engine, state):
    from meridian.persistence.models import AccountMember

    clock = [NOW]
    app, _ = configured(engine, clock=lambda: clock[0])

    async def check(client):
        assert (await login(client)).status_code == 200
        if state == "expired":
            clock[0] += timedelta(minutes=5)
        else:
            with Session(engine) as db, db.begin():
                db.get(AccountMember, (ACCOUNT, SUBJECTS[0])).revoked_at = NOW
        response = await client.get(PREFIX + "/current")
        assert response.status_code == 401
        assert_private(response)
        assert "subject" not in response.json()

    scenario(app, check)


def test_setup_revokes_prior_sessions_and_issues_cookie_after_password_update(engine):
    from meridian.security.supabase_auth import PasswordSetup

    class SetupProvider(Provider):
        async def verify_setup(self, token_hash, kind):
            assert token_hash.get_secret_value() == "f" * 64 and kind == "signup"
            return PasswordSetup(
                VerifiedIdentity(SUBJECTS[0], NOW + timedelta(minutes=5)),
                SecretStr("invented-access"),
            )

        async def set_password(self, setup, password):
            # No transaction/connection remains open across this provider await.
            with Session(engine) as db:
                assert all(row.revoked_at is not None for row in db.scalars(select(AppSession)))
            assert password.get_secret_value() == PASSWORD
            return setup.identity

    app, _provider = configured(engine, provider=SetupProvider())

    async def operation(client):
        assert (await login(client)).status_code == 200
        old = client.cookies[SESSION_COOKIE]
        nonce = await bootstrap(client)
        response = await client.post(
            PREFIX + "/setup",
            headers={"origin": ORIGIN, "x-csrf-token": nonce},
            json={"token_hash": "f" * 64, "type": "signup", "password": PASSWORD},
        )
        assert response.status_code == 200
        assert client.cookies[SESSION_COOKIE] != old
        assert_private(response)
        client.cookies.set(SESSION_COOKIE, old, domain="synthetic.example", path="/")
        assert (await client.get(PREFIX + "/current")).status_code == 401

    scenario(app, operation)


def test_setup_denies_nonmember_before_password_change(engine):
    from meridian.security.supabase_auth import PasswordSetup

    class NonmemberProvider(Provider):
        async def verify_setup(self, token_hash, kind):
            return PasswordSetup(
                VerifiedIdentity(
                    "33333333-3333-4333-8333-333333333333", NOW + timedelta(minutes=5)
                ),
                SecretStr("invented-access"),
            )

        async def set_password(self, *_args):
            pytest.fail("Nonmember must not change password")

    app, _ = configured(engine, provider=NonmemberProvider())

    async def operation(client):
        nonce = await bootstrap(client)
        response = await client.post(
            PREFIX + "/setup",
            headers={"origin": ORIGIN, "x-csrf-token": nonce},
            json={"token_hash": "f" * 64, "type": "recovery", "password": PASSWORD},
        )
        assert response.status_code == 401 and not response.headers.get_list("set-cookie")

    scenario(app, operation)
