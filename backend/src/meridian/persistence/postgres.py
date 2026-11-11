"""Bounded PostgreSQL maintenance support, not hosted authorization or deployment.

Connections use synchronous pg8000 and no process-owned pool. Verified TLS is
mandatory outside an explicitly requested disposable loopback test connection.
Do not display an Engine URL or pass raw driver errors to a browser/log.
"""

import ssl
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, Engine, create_engine, make_url
from sqlalchemy.pool import NullPool

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class PostgresConfigurationError(ValueError):
    """Safe configuration category; supplied DSNs are never included."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class PostgresOperationError(RuntimeError):
    """Safe database-operation category; raw driver errors remain private."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def create_postgres_engine(
    database_url: str | URL, *, allow_loopback_insecure: bool = False
) -> Engine:
    """Build a lazy engine with explicit TLS/driver settings and bounded timeout.

    URL query options are intentionally unsupported: they must not override TLS,
    host routing or connection behavior. Use the typed construction arguments.
    Loopback plaintext is for a disposable local/CI PostgreSQL service only.
    Engine construction performs no network call and no schema mutation.
    """
    try:
        url = make_url(database_url)
    except Exception:
        raise PostgresConfigurationError("postgres_url_invalid") from None
    if url.drivername != "postgresql+pg8000":
        raise PostgresConfigurationError("postgres_driver_invalid")
    if not url.host or not url.username or not url.database:
        raise PostgresConfigurationError("postgres_url_incomplete")
    if url.query:
        raise PostgresConfigurationError("postgres_url_options_unsupported")
    if not isinstance(allow_loopback_insecure, bool):
        raise PostgresConfigurationError("postgres_tls_option_invalid")
    if allow_loopback_insecure and url.host.lower() not in _LOOPBACK_HOSTS:
        raise PostgresConfigurationError("postgres_insecure_host_forbidden")
    ssl_context = False if allow_loopback_insecure else ssl.create_default_context()
    try:
        return create_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            client_encoding="utf8",
            connect_args={"ssl_context": ssl_context, "timeout": 10},
        )
    except Exception:
        raise PostgresConfigurationError("postgres_engine_unavailable") from None


def upgrade_postgres_database(engine: Engine, *, revision: str = "head") -> None:
    """Run reviewed migrations in an explicitly supplied PostgreSQL transaction.

    This maintenance operation does not bootstrap a production user, configure
    Supabase Auth, or select a deployment. It requires the source checkout and
    a separately verified backup before upgrading existing financial data.
    """
    if engine.dialect.name != "postgresql":
        raise PostgresConfigurationError("postgres_engine_required")
    config_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    if not config_path.is_file():
        raise PostgresConfigurationError("postgres_migrations_missing")
    try:
        config = Config(str(config_path))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
    except Exception:
        raise PostgresOperationError("postgres_migration_failed") from None
