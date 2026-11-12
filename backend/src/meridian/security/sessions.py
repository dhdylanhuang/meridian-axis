"""Opaque sessions for a verified provider identity; callers own transactions.

No HTTP routes or provider refresh material are added here. Each operation must
run in a short, request-owned SQLAlchemy Session and commit its audit atomically.
"""

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import SecretStr
from sqlalchemy import exists, update
from sqlalchemy.orm import Session

from meridian.persistence.models import AccountMember, AppSession, AuditRecord
from meridian.security.supabase_auth import VerifiedIdentity


class SessionError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SessionPrincipal:
    account_id: str
    subject: str
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    token: SecretStr
    csrf_token: SecretStr
    expires_at: datetime


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise SessionError("session_clock_invalid")
    return value.astimezone(UTC)


def _hash(value: str | SecretStr | None, code: str) -> str:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise SessionError(code)
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class SessionService:
    def __init__(self, account_id: str, origin: str, *, max_age_seconds: int = 3600):
        if not isinstance(account_id, str) or not 1 <= len(account_id) <= 64:
            raise SessionError("session_configuration_invalid")
        try:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or any(char.isspace() for char in origin)
                or origin != "https://" + parsed.netloc
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)
            ):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise SessionError("session_configuration_invalid") from None
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 3600:
            raise SessionError("session_configuration_invalid")
        self.account_id, self.origin = account_id, origin
        self.max_age = timedelta(seconds=max_age_seconds)

    def _member(self, db: Session, subject: str, now: datetime) -> AccountMember:
        member = db.get(AccountMember, (self.account_id, subject), populate_existing=True)
        if member is None or member.created_at > now or member.revoked_at is not None:
            raise SessionError("membership_unavailable")
        return member

    def _audit(self, db: Session, subject: str, now: datetime, action: str) -> None:
        # Audit the account and subject, never a raw token or token/CSRF hash.
        db.add(
            AuditRecord(
                id=uuid4().hex,
                occurred_at=now,
                actor=subject,
                action=action,
                entity_type="account",
                entity_id=self.account_id,
                details_json="{}",
            )
        )

    def _issue(self, db: Session, subject: str, now: datetime, expiry: datetime) -> IssuedSession:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.add(
            AppSession(
                token_hash=_hash(token, "session_invalid"),
                account_id=self.account_id,
                auth_subject=subject,
                csrf_hash=_hash(csrf, "csrf_invalid"),
                created_at=now,
                expires_at=expiry,
            )
        )
        return IssuedSession(SecretStr(token), SecretStr(csrf), expiry)

    def issue(self, db: Session, identity: VerifiedIdentity, *, now: datetime) -> IssuedSession:
        now = _utc(now)
        if not isinstance(identity, VerifiedIdentity):
            raise SessionError("provider_identity_invalid")
        expiry = min(_utc(identity.expires_at), now + self.max_age)
        if expiry <= now:
            raise SessionError("provider_identity_expired")
        self._member(db, identity.subject, now)
        result = self._issue(db, identity.subject, now, expiry)
        self._audit(db, identity.subject, now, "session_login")
        db.flush()
        return result

    def _load(self, db: Session, token: str | SecretStr | None, now: datetime) -> AppSession:
        record = db.get(AppSession, _hash(token, "session_invalid"), populate_existing=True)
        if record is None or record.account_id != self.account_id:
            raise SessionError("session_invalid")
        if record.revoked_at is not None:
            raise SessionError("session_revoked")
        if record.created_at > now or record.expires_at <= now:
            raise SessionError("session_expired")
        self._member(db, record.auth_subject, now)
        return record

    def authenticate(self, db: Session, token: str | SecretStr | None, *, now: datetime):
        record = self._load(db, token, _utc(now))
        return SessionPrincipal(record.account_id, record.auth_subject, record.expires_at)

    def _mutation(self, db, token, csrf_token, origin, now):
        if origin != self.origin:
            raise SessionError("origin_invalid")
        record = self._load(db, token, now)
        if not hmac.compare_digest(_hash(csrf_token, "csrf_invalid"), record.csrf_hash):
            raise SessionError("csrf_invalid")
        return record

    def authorize_mutation(self, db, token, *, csrf_token, origin, now: datetime):
        record = self._mutation(db, token, csrf_token, origin, _utc(now))
        return SessionPrincipal(record.account_id, record.auth_subject, record.expires_at)

    def revoke(self, db, token, *, csrf_token, origin, now: datetime) -> None:
        now = _utc(now)
        record = self._mutation(db, token, csrf_token, origin, now)
        self._consume(db, record, now)
        self._audit(db, record.auth_subject, now, "session_logout")
        db.flush()

    def rotate(self, db, token, *, csrf_token, origin, now: datetime) -> IssuedSession:
        now = _utc(now)
        record = self._mutation(db, token, csrf_token, origin, now)
        self._consume(db, record, now)
        result = self._issue(db, record.auth_subject, now, record.expires_at)
        self._audit(db, record.auth_subject, now, "session_rotate")
        db.flush()
        return result

    def _consume(self, db: Session, record: AppSession, now: datetime) -> None:
        active_member = exists().where(
            AccountMember.account_id == self.account_id,
            AccountMember.auth_subject == record.auth_subject,
            AccountMember.revoked_at.is_(None),
            AccountMember.created_at <= now,
        )
        changed = db.execute(
            update(AppSession)
            .where(
                AppSession.token_hash == record.token_hash,
                AppSession.account_id == self.account_id,
                AppSession.revoked_at.is_(None),
                AppSession.expires_at > now,
                active_member,
            )
            .values(revoked_at=now)
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            raise SessionError("session_revoked")
