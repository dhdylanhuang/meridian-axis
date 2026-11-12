"""Fresh password-login qualifier, not a refresh/session or membership service.

Provider contract: https://github.com/supabase/auth/blob/master/openapi.yaml
Provider tokens stay within sign_in and never become browser/application tokens.
"""

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
from pydantic import SecretStr

_MAX_BODY = 65_536


class AuthError(ValueError):
    """Only fixed categories cross the adapter boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class VerifiedIdentity:
    subject: str
    expires_at: datetime


def _subject(value) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise AuthError("auth_response_invalid") from None
    return value


class SupabaseAuthClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        project_ref: str,
        publishable_key: SecretStr,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if not isinstance(project_ref, str) or not re.fullmatch(r"[a-z]{20}", project_ref):
            raise AuthError("auth_configuration_invalid")
        if not isinstance(publishable_key, SecretStr) or not re.fullmatch(
            r"sb_publishable_[A-Za-z0-9_-]{1,256}", publishable_key.get_secret_value()
        ):
            raise AuthError("auth_configuration_invalid")
        self._client = client
        self._origin = f"https://{project_ref}.supabase.co"
        self._key = publishable_key
        self._clock = clock

    def _now(self) -> datetime:
        try:
            value = self._clock()
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError
            return value.astimezone(UTC)
        except Exception:
            raise AuthError("auth_clock_invalid") from None

    async def _request(self, method, path, *, body=None, bearer=None):
        headers = {"apikey": self._key.get_secret_value(), "Accept": "application/json"}
        if bearer is not None:
            headers["Authorization"] = "Bearer " + bearer
        # Construct directly: injected client defaults cannot alter origin, query,
        # cookies or Authorization. The caller owns the client's transport/hooks.
        request = httpx.Request(
            method,
            self._origin + path,
            headers=headers,
            json=body,
            extensions={"timeout": httpx.Timeout(10).as_dict()},
        )
        response = None
        try:
            async with asyncio.timeout(20):
                response = await self._client.send(
                    request, stream=True, follow_redirects=False, auth=None
                )
                if response.status_code == 429:
                    raise AuthError("auth_rate_limited")
                if response.status_code >= 500:
                    raise AuthError("auth_unavailable")
                if response.status_code in (400, 401, 403, 422):
                    raise AuthError("auth_rejected")
                if response.status_code != 200:
                    raise AuthError("auth_response_invalid")
                if (
                    response.headers.get("content-type", "").split(";")[0].strip()
                    != "application/json"
                ):
                    raise AuthError("auth_response_invalid")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > _MAX_BODY:
                        raise AuthError("auth_response_invalid")
                    content.extend(chunk)
                try:
                    payload = json.loads(content)
                except (ValueError, UnicodeError):
                    raise AuthError("auth_response_invalid") from None
                if not isinstance(payload, dict):
                    raise AuthError("auth_response_invalid")
                return payload
        except AuthError:
            raise
        except Exception:
            raise AuthError("auth_unavailable") from None
        finally:
            if response is not None:
                try:
                    await response.aclose()
                except Exception:
                    raise AuthError("auth_unavailable") from None

    async def sign_in(self, email: str, password: SecretStr) -> VerifiedIdentity:
        if (
            not isinstance(email, str)
            or not email.strip()
            or len(email) > 1024
            or not isinstance(password, SecretStr)
            or not 0 < len(password.get_secret_value()) <= 4096
        ):
            raise AuthError("auth_input_invalid")
        started = self._now()
        payload = await self._request(
            "POST",
            "/auth/v1/token?grant_type=password",
            body={"email": email, "password": password.get_secret_value()},
        )
        try:
            access = payload["access_token"]
            lifetime, expiry = payload["expires_in"], payload["expires_at"]
            if (
                not isinstance(access, str)
                or not re.fullmatch(r"[A-Za-z0-9._~-]{1,16384}", access)
                or payload["token_type"] != "bearer"
                or type(lifetime) is not int
                or lifetime <= 0
                or type(expiry) is not int
            ):
                raise ValueError
            subject = _subject(payload["user"]["id"])
            expires_at = min(
                datetime.fromtimestamp(expiry, UTC), started + timedelta(seconds=lifetime)
            )
        except Exception:
            raise AuthError("auth_response_invalid") from None
        if expires_at <= self._now():
            raise AuthError("auth_expired")
        user = await self._request("GET", "/auth/v1/user", bearer=access)
        if _subject(user.get("id")) != subject:
            raise AuthError("auth_subject_mismatch")
        if expires_at <= self._now():
            raise AuthError("auth_expired")
        return VerifiedIdentity(subject, expires_at)
