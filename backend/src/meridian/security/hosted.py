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
async def hosted_application(binding, *, origin, project_ref, publishable_key, login_csrf_key):
    """Own all resources for one serialised Durable Object request.

    No database socket is opened until a route needs it. NullPool prevents a
    connection surviving the request. Credentials stay in the binding/closure,
    outside SQLAlchemy URLs, exceptions emitted by this boundary and logs.
    """
    engine = None
    try:
        service = SessionService("shared-isa", origin)
        user, password = binding.user, binding.password
        host, database = binding.host, binding.database
        port = int(binding.port)
        if (
            user != "meridian_bff_public"
            or database != "postgres"
            or not isinstance(password, str)
            or not password
            or not isinstance(host, str)
            or not host
            or any(char.isspace() for char in host)
            or not 1 <= port <= 65535
            or not isinstance(publishable_key, SecretStr)
            or not isinstance(login_csrf_key, SecretStr)
        ):
            raise ValueError

        def connect():
            # Only the provider's Worker-to-Hyperdrive local hop omits TLS.
            # The separately qualified Supabase origin requires TLS + WebPKI.
            return pg8000.dbapi.connect(
                user=user,
                password=password,
                host=host,
                port=port,
                database=database,
                ssl_context=False,
                timeout=10,
            )

        engine = create_engine(
            "postgresql+pg8000://",
            creator=connect,
            poolclass=NullPool,
            hide_parameters=True,
            echo=False,
        )
        database_factory = sessionmaker(bind=engine, expire_on_commit=False)
        async with httpx.AsyncClient() as client:
            provider = SupabaseAuthClient(client, project_ref, publishable_key)
            handler = SessionHttp(
                service,
                provider,
                database_factory,
                DatabaseLoginLimiter(database_factory, "shared-login"),
                login_csrf_key,
            )
            yield create_app(session_http=handler)
    finally:
        if engine is not None:
            engine.dispose()
