"""Request-owned application wiring for a verified Hyperdrive binding.

This factory never migrates, provisions identities or accepts a database URL.
The binding's origin must independently enforce verified TLS and disable caches.
"""

from contextlib import asynccontextmanager

import httpx
import pg8000.dbapi
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from meridian.app import create_app
from meridian.security.http import SessionHttp
from meridian.security.login_limiter import DatabaseLoginLimiter
from meridian.security.sessions import SessionService
from meridian.security.supabase_auth import SupabaseAuthClient


@asynccontextmanager
async def hosted_application(
    binding, *, origin, project_ref, publishable_key, login_csrf_key, refresh=None
):
    """Own all resources for one serialised Durable Object request.

    No database socket is opened until a route needs it. NullPool prevents a
    connection surviving the request. Credentials stay in the binding/closure,
    outside SQLAlchemy URLs, exceptions emitted by this boundary and logs.
    """
    engine = None
    if not isinstance(publishable_key, SecretStr) or not isinstance(login_csrf_key, SecretStr):
        raise ValueError("binding_secret_type_invalid")
    try:
        service = SessionService("shared-isa", origin)
        engine = create_binding_engine(binding)
        database_factory = sessionmaker(bind=engine, expire_on_commit=False)
        async with httpx.AsyncClient() as client:
            provider = SupabaseAuthClient(client, project_ref, publishable_key)
            handler = SessionHttp(
                service,
                provider,
                database_factory,
                DatabaseLoginLimiter(database_factory, "shared-login"),
                login_csrf_key,
                refresh=refresh,
            )
            yield create_app(session_http=handler)
    finally:
        if engine is not None:
            engine.dispose()


def create_binding_engine(binding, *, expected_role="meridian_bff_public"):
    """Use only the qualified Hyperdrive hop, verifying the origin identity."""
    if expected_role not in {"meridian_bff_public", "meridian_sync_public"}:
        raise ValueError("runtime_database_identity_invalid")
    user, password = binding.user, binding.password
    host, database = binding.host, binding.database
    port = int(binding.port)
    checks = (
        (isinstance(user, str) and bool(user), "binding_user_invalid"),
        (isinstance(database, str) and bool(database), "binding_database_invalid"),
        (isinstance(password, str) and bool(password), "binding_password_invalid"),
        (
            isinstance(host, str) and bool(host) and not any(c.isspace() for c in host),
            "binding_host_invalid",
        ),
        (1 <= port <= 65535, "binding_port_invalid"),
    )
    for valid, code in checks:
        if not valid:
            raise ValueError(code)

    def connect():
        # Only the provider's Worker-to-Hyperdrive local hop omits TLS.
        # The separately qualified Supabase origin requires TLS + WebPKI.
        connection = pg8000.dbapi.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            ssl_context=False,
            timeout=10,
        )
        # Hyperdrive's local credentials may be proxy aliases. Verify the
        # authenticated origin identity before SQLAlchemy or any service
        # can use the connection; never trust a local username as proof.
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT current_user, current_database(), current_schema()")
            if tuple(cursor.fetchone()) != (expected_role, "postgres", "public"):
                raise RuntimeError("runtime_database_identity_invalid")
            connection.rollback()
            cursor.close()
            return connection
        except Exception:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
            try:
                connection.close()
            except Exception:
                pass
            raise RuntimeError("runtime_database_identity_invalid") from None

    return create_engine(
        "postgresql+pg8000://",
        creator=connect,
        poolclass=NullPool,
        hide_parameters=True,
        echo=False,
    )
