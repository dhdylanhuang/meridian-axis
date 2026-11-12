"""Explicit HTTPS session transport; requires provider, database and shared limiter.

No in-process production limiter or provider refresh is supplied. A deployment
must qualify its proxy trust, database permissions and shared atomic limiter.
"""

import asyncio
import hashlib
import hmac
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import APIRouter, Request
from pydantic import SecretStr
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from meridian.security.sessions import SessionError, SessionService
from meridian.security.supabase_auth import AuthError, SupabaseAuthClient

SESSION_COOKIE = "__Host-meridian_session"
CSRF_COOKIE = "__Host-meridian_csrf"
LOGIN_COOKIE = "__Host-meridian_login"
PREFIX = "/api/v1/session"
_NONCE = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("request_invalid")
        result[key] = value
    return result


def private_response(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(
        body,
        status_code=status,
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


class SessionHttp:
    def __init__(
        self,
        service: SessionService,
        provider: SupabaseAuthClient,
        database: Callable[[], Session],
        login_limiter: Callable[[], Awaitable[bool]],
        login_csrf_key: SecretStr,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if (
            not isinstance(login_csrf_key, SecretStr)
            or not 32 <= len(login_csrf_key.get_secret_value().encode()) <= 1024
            or not callable(database)
            or not callable(login_limiter)
        ):
            raise ValueError("session_http_configuration_invalid")
        self.service, self.provider = service, provider
        self.database, self.login_limiter = database, login_limiter
        self._key, self._clock = login_csrf_key, clock

    def _now(self):
        now = self._clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise RuntimeError("session_clock_invalid")
        return now.astimezone(UTC)

    def _signature(self, value):
        return hmac.new(
            self._key.get_secret_value().encode(), value.encode("ascii"), hashlib.sha256
        ).hexdigest()

    def _cookie(self, request, name):
        # Reject duplicates instead of letting a parser choose a credential.
        matches = []
        for header in request.headers.getlist("cookie"):
            for part in header.split(";"):
                key, separator, value = part.strip().partition("=")
                if key == name and separator:
                    matches.append(value)
        if len(matches) != 1:
            raise SessionError("session_invalid")
        return matches[0]

    def _header(self, request, name):
        values = request.headers.getlist(name)
        return values[0] if len(values) == 1 else None

    def _origin(self, request):
        if self._header(request, "origin") != self.service.origin:
            raise SessionError("origin_invalid")

    def _login_csrf(self, request, now):
        try:
            nonce, timestamp, signature = self._cookie(request, LOGIN_COOKIE).split(".")
            submitted = self._header(request, "x-csrf-token")
            if (
                not _NONCE.fullmatch(nonce)
                or not re.fullmatch(r"[0-9]{1,12}", timestamp)
                or not re.fullmatch(r"[0-9a-f]{64}", signature)
                or not isinstance(submitted, str)
                or not _NONCE.fullmatch(submitted)
                or not hmac.compare_digest(nonce, submitted)
                or not hmac.compare_digest(self._signature(nonce + "." + timestamp), signature)
                or not 0 <= now.timestamp() - int(timestamp) <= 300
            ):
                raise ValueError
        except (ValueError, SessionError):
            raise SessionError("csrf_invalid") from None

    async def _credentials(self, request, *, setup=False):
        if self._header(request, "content-type") != "application/json":
            raise ValueError("request_invalid")
        body = bytearray()
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                if len(body) + len(chunk) > 8192:
                    raise ValueError("request_invalid")
                body.extend(chunk)
        try:
            value = json.loads(body, object_pairs_hook=_unique_fields)
        except (ValueError, UnicodeError):
            raise ValueError("request_invalid") from None
        fields = {"token_hash", "type", "password"} if setup else {"email", "password"}
        if (
            not isinstance(value, dict)
            or set(value) != fields
            or not all(isinstance(item, str) for item in value.values())
        ):
            raise ValueError("request_invalid")
        if setup:
            if (
                value["type"] not in {"signup", "recovery"}
                or not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value["token_hash"])
                or not 12 <= len(value["password"]) <= 128
            ):
                raise ValueError("request_invalid")
            return SecretStr(value["token_hash"]), value["type"], SecretStr(value["password"])
        if not 1 <= len(value["email"]) <= 1024 or not 1 <= len(value["password"]) <= 4096:
            raise ValueError("request_invalid")
        return value["email"], SecretStr(value["password"])

    def _issued(self, issued):
        age = int((issued.expires_at - self._now()).total_seconds())
        if age <= 0:
            raise SessionError("session_expired")
        response = private_response({"expires_at": issued.expires_at.isoformat()})
        for name, value, http_only in (
            (SESSION_COOKIE, issued.token, True),
            (CSRF_COOKIE, issued.csrf_token, False),
        ):
            response.set_cookie(
                name,
                value.get_secret_value(),
                max_age=age,
                expires=issued.expires_at,
                path="/",
                secure=True,
                httponly=http_only,
                samesite="strict",
            )
        response.delete_cookie(
            LOGIN_COOKIE, path="/", secure=True, httponly=True, samesite="strict"
        )
        return response

    async def handle(self, request, operation):
        try:
            # Trust only ASGI scheme/authority; proxy handling is a deployment gate.
            authority = f"{request.url.scheme}://{request.url.netloc}"
            if (
                authority != self.service.origin
                or request.url.scheme != "https"
                or len(request.headers.getlist("host")) != 1
                or request.url.query
                or (
                    request.headers.getlist("origin")
                    and self._header(request, "origin") != self.service.origin
                )
            ):
                return private_response({"error": "origin_invalid"}, 403)
            now = self._now()
            if operation == "bootstrap":
                nonce = secrets.token_urlsafe(32)
                value = nonce + "." + str(int(now.timestamp()))
                response = private_response({"csrf_token": nonce})
                response.set_cookie(
                    LOGIN_COOKIE,
                    value + "." + self._signature(value),
                    max_age=300,
                    path="/",
                    secure=True,
                    httponly=True,
                    samesite="strict",
                )
                return response
            if operation in {"login", "setup"}:
                self._origin(request)
                self._login_csrf(request, now)
                async with asyncio.timeout(5):
                    permitted = await self.login_limiter()
                if permitted is not True:
                    return private_response({"error": "login_rate_limited"}, 429)
                if operation == "setup":
                    token_hash, kind, password = await self._credentials(request, setup=True)
                    setup = await self.provider.verify_setup(token_hash, kind)
                    with self.database() as db, db.begin():
                        self.service.require_member(db, setup.identity, now=self._now())
                        self.service.revoke_subject(db, setup.identity.subject, now=self._now())
                    identity = await self.provider.set_password(setup, password)
                else:
                    email, password = await self._credentials(request)
                    identity = await self.provider.sign_in(email, password)
                with self.database() as db, db.begin():
                    issued = self.service.issue(db, identity, now=self._now())
                return self._issued(issued)
            token = self._cookie(request, SESSION_COOKIE)
            with self.database() as db, db.begin():
                if operation == "current":
                    principal = self.service.authenticate(db, token, now=now)
                    return private_response(
                        {
                            "subject": principal.subject,
                            "expires_at": principal.expires_at.isoformat(),
                        }
                    )
                self._origin(request)
                arguments = {
                    "csrf_token": self._header(request, "x-csrf-token"),
                    "origin": self.service.origin,
                    "now": now,
                }
                if operation == "rotate":
                    issued = self.service.rotate(db, token, **arguments)
                else:
                    self.service.revoke(db, token, **arguments)
            if operation == "rotate":
                return self._issued(issued)
            response = private_response({"status": "signed_out"})
            for name in (SESSION_COOKIE, CSRF_COOKIE, LOGIN_COOKIE):
                response.delete_cookie(
                    name, path="/", secure=True, httponly=name != CSRF_COOKIE, samesite="strict"
                )
            return response
        except SessionError as error:
            status = 403 if error.code in {"origin_invalid", "csrf_invalid"} else 401
            return private_response({"error": "request_denied"}, status)
        except AuthError as error:
            status = {"auth_rejected": 401, "auth_rate_limited": 429}.get(error.code, 503)
            return private_response({"error": "login_unavailable"}, status)
        except ValueError:
            return private_response({"error": "request_invalid"}, 400)
        except Exception:
            return private_response({"error": "session_unavailable"}, 503)

    def router(self):
        router = APIRouter(prefix=PREFIX)

        @router.get("/bootstrap")
        async def bootstrap(request: Request):
            return await self.handle(request, "bootstrap")

        @router.post("/login")
        async def login(request: Request):
            return await self.handle(request, "login")

        @router.post("/setup")
        async def setup(request: Request):
            return await self.handle(request, "setup")

        @router.get("/current")
        async def current(request: Request):
            return await self.handle(request, "current")

        @router.post("/rotate")
        async def rotate(request: Request):
            return await self.handle(request, "rotate")

        @router.post("/logout")
        async def logout(request: Request):
            return await self.handle(request, "logout")

        return router
