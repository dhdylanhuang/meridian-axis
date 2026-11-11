"""Run migrations against an explicitly supplied SQLite database.

Programmatic callers should pass config.attributes['connection']. For direct
Alembic use, set sqlalchemy.url explicitly; there is no implicit production DB.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from meridian.persistence.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name, disable_existing_loggers=False)
target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise ValueError("An explicit sqlalchemy.url is required")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_on_connection(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    supplied_connection = config.attributes.get("connection")
    if supplied_connection is not None:
        _run_on_connection(supplied_connection)
        return
    if not config.get_main_option("sqlalchemy.url"):
        raise ValueError("An explicit sqlalchemy.url or supplied connection is required")
    engine = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            _run_on_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
