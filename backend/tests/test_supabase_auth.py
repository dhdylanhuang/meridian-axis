"""Synthetic GoTrue password and GET /user fixtures; no provider calls."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from meridian.security.supabase_auth import AuthError, SupabaseAuthClient, VerifiedIdentity

PROJECT = "abcdefghijklmnopqrst"
SUBJECT = "9c5a50c2-f8d2-4571-9347-8a2f497d05bb"
OTHER = "537e152f-bfab-4306-b3e0-7b52ef955468"
NOW = datetime(2026, 1, 2, 12, tzinfo=UTC)
KEY = "sb_publishable_syntheticPrivateKey"
PASSWORD = "invented-password-private"
ACCESS = "synthetic.access-private.token"
REFRESH = "synthetic-refresh-private"


def token():
    return {
        "access_token": ACCESS,
        "refresh_token": REFRESH,
        "token_type": "bearer",
        "expires_in": 3600,
        "expires_at": int(NOW.timestamp()) + 3600,
        "user": {"id": SUBJECT},
    }


def run(handler, *, clock=lambda: NOW, email="synthetic@example.invalid", password=None):
    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            follow_redirects=True,
            base_url="https://unsafe.invalid",
            params={"unsafe": "private"},
            auth=("unrelated", "private"),
            headers={"authorization": "unrelated-private"},
            cookies={"unrelated-cookie": "invented-private-cookie"},
        ) as http:
            api = SupabaseAuthClient(http, PROJECT, SecretStr(KEY), clock=clock)
            result = await api.sign_in(email, password or SecretStr(PASSWORD))
            assert not http.is_closed
            for sensitive in (KEY, PASSWORD, ACCESS, REFRESH):
                assert sensitive not in repr(api)
                assert sensitive not in repr(result)
            return result

    return asyncio.run(scenario())


def test_success_checks_user_over_http_and_keeps_only_identity():
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.scheme == "https"
        assert request.url.host == PROJECT + ".supabase.co"
        assert request.headers["apikey"] == KEY
        assert "cookie" not in request.headers
        assert "unsafe" not in request.url.params
        assert all(value == 10 for value in request.extensions["timeout"].values())
        if request.method == "POST":
            assert request.url.path == "/auth/v1/token"
            assert str(request.url.query, "ascii") == "grant_type=password"
            assert "authorization" not in request.headers
            assert json.loads(request.content) == {
                "email": "synthetic@example.invalid",
                "password": PASSWORD,
            }
            return httpx.Response(
                200,
                json=token(),
                headers={"set-cookie": "provider_cookie=invented-private-cookie; Path=/; Secure"},
            )
        assert request.method == "GET" and request.url.path == "/auth/v1/user"
        assert request.headers["authorization"] == "Bearer " + ACCESS
        return httpx.Response(200, json={"id": SUBJECT, "email": "ignored@example.invalid"})

    assert run(handler) == VerifiedIdentity(SUBJECT, NOW + timedelta(hours=1))
    assert len(requests) == 2


@pytest.mark.parametrize(
    "status,code",
    [
        (400, "auth_rejected"),
        (401, "auth_rejected"),
        (403, "auth_rejected"),
        (422, "auth_rejected"),
        (429, "auth_rate_limited"),
        (500, "auth_unavailable"),
        (503, "auth_unavailable"),
        (302, "auth_response_invalid"),
    ],
)
def test_provider_errors_and_redirects_are_safe(status, code, caplog):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status,
            headers={"location": "https://unsafe.invalid/?secret=" + ACCESS},
            text=PASSWORD + KEY + REFRESH,
        )

    with pytest.raises(AuthError) as caught:
        run(handler)
    assert str(caught.value) == code
    assert len(calls) == 1
    for sensitive in (KEY, PASSWORD, ACCESS, REFRESH):
        assert sensitive not in caplog.text
        assert sensitive not in repr(caught.value)


@pytest.mark.parametrize(
    "change",
    [
        {"access_token": None},
        {"access_token": "bad\r\nheader"},
        {"token_type": "unexpected"},
        {"expires_in": True},
        {"expires_at": "private"},
        {"user": {"id": "not-a-uuid"}},
        {"user": {"id": SUBJECT.upper()}},
    ],
)
def test_malformed_token_fields_are_rejected_before_user_request(change):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=token() | change)

    with pytest.raises(AuthError, match="auth_response_invalid"):
        run(handler)
    assert len(calls) == 1


def test_subject_mismatch_never_returns_identity():
    def handler(request):
        return httpx.Response(200, json=token() if request.method == "POST" else {"id": OTHER})

    with pytest.raises(AuthError, match="auth_subject_mismatch"):
        run(handler)


def test_expiry_checked_before_and_after_user_verification():
    for expires_after in (0, 1):
        calls = []

        def handler(request, calls=calls):
            calls.append(request)
            return httpx.Response(
                200, json=token() if request.method == "POST" else {"id": SUBJECT}
            )

        times = iter(
            [NOW, NOW + timedelta(hours=1)]
            if expires_after == 0
            else [NOW, NOW, NOW + timedelta(hours=1)]
        )
        with pytest.raises(AuthError, match="auth_expired"):
            run(handler, clock=lambda times=times: next(times))
        assert len(calls) == expires_after + 1


@pytest.mark.parametrize("kind", ["oversize", "not_json", "array", "wrong_content_type", "network"])
def test_response_limits_and_transport_failures(kind):
    def handler(request):
        if kind == "network":
            raise httpx.ReadTimeout(PASSWORD + ACCESS, request=request)
        if kind == "oversize":
            return httpx.Response(
                200, content=b"x" * 65537, headers={"content-type": "application/json"}
            )
        if kind == "not_json":
            return httpx.Response(200, text=PASSWORD, headers={"content-type": "application/json"})
        if kind == "array":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=token(), headers={"content-type": "text/plain"})

    with pytest.raises(AuthError) as caught:
        run(handler)
    assert caught.value.code in {"auth_response_invalid", "auth_unavailable"}
    assert PASSWORD not in repr(caught.value)


@pytest.mark.parametrize(
    "project", ["https://unsafe.invalid", PROJECT + ".unsafe", PROJECT + "\n", "A" * 20]
)
def test_project_reference_cannot_supply_unsafe_url(project):
    with pytest.raises(AuthError, match="auth_configuration_invalid"):
        SupabaseAuthClient(None, project, SecretStr(KEY))


def test_publishable_key_is_secret_and_rejects_server_secret():
    assert KEY not in repr(SecretStr(KEY))
    with pytest.raises(AuthError, match="auth_configuration_invalid"):
        SupabaseAuthClient(None, PROJECT, SecretStr("sb_secret_private"))


def test_naive_clock_is_rejected_before_http():
    with pytest.raises(AuthError, match="auth_clock_invalid"):
        run(
            lambda _request: pytest.fail("No network expected"),
            clock=lambda: NOW.replace(tzinfo=None),
        )


@pytest.mark.parametrize("status", [401, 503, 302])
def test_user_verification_failure_cannot_issue_identity(status):
    calls = []

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json=token())
        return httpx.Response(status, text=ACCESS + PASSWORD)

    with pytest.raises(AuthError):
        run(handler)
    assert len(calls) == 2


def test_oversized_stream_is_closed_on_rejection():
    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"x" * 32768
            yield b"x" * 32769
            pytest.fail("The adapter must stop consuming the oversized response")

        async def aclose(self):
            self.closed = True

    stream = Stream()
    with pytest.raises(AuthError, match="auth_response_invalid"):
        run(
            lambda _request: httpx.Response(
                200, stream=stream, headers={"content-type": "application/json"}
            )
        )
    assert stream.closed


def test_setup_verifies_subject_and_updates_password_without_exposing_access():
    async def scenario():
        calls = []

        def handler(request):
            calls.append(request)
            if request.url.path == "/auth/v1/verify":
                assert json.loads(request.content) == {"token_hash": "f" * 64, "type": "recovery"}
                return httpx.Response(200, json=token())
            if request.method == "PUT":
                assert json.loads(request.content) == {"password": PASSWORD}
            assert request.headers["authorization"] == "Bearer " + ACCESS
            return httpx.Response(200, json={"id": SUBJECT})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            api = SupabaseAuthClient(http, PROJECT, SecretStr(KEY), clock=lambda: NOW)
            setup = await api.verify_setup(SecretStr("f" * 64), "recovery")
            assert ACCESS not in repr(setup)
            identity = await api.set_password(setup, SecretStr(PASSWORD))
            assert identity.subject == SUBJECT and ACCESS not in repr(identity)
        assert [x.method for x in calls] == ["POST", "GET", "PUT"]

    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["signup", "recovery"])
def test_setup_rejects_different_authenticated_subject(kind):
    async def scenario():
        def handler(request):
            return httpx.Response(200, json=token() if request.method == "POST" else {"id": OTHER})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            api = SupabaseAuthClient(http, PROJECT, SecretStr(KEY), clock=lambda: NOW)
            with pytest.raises(AuthError, match="auth_subject_mismatch"):
                await api.verify_setup(SecretStr("f" * 64), kind)

    asyncio.run(scenario())
