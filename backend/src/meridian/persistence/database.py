"""SQLite connection policy. Each request/job owns its short-lived Session."""

from pathlib import Path

from sqlalchemy import URL, Engine, create_engine, event


def create_db_engine(path: Path) -> Engine:
    """Create a file-backed SQLite engine without creating schema or directories.

    WAL permits readers during a short writer transaction. It does not permit
    multiple scheduler owners or make a network filesystem safe for SQLite.
    """
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(path.resolve())),
        connect_args={"check_same_thread": False, "timeout": 5.0},
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def configure_connection(connection, _record):
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=FULL")
        finally:
            cursor.close()

    return engine


def upgrade_database(path: Path) -> None:
    """Apply reviewed migrations explicitly from the source checkout.

    This is a maintenance operation, never an automatic HTTP startup action.
    Back up an existing database before applying a later schema upgrade.
    """
    from alembic import command
    from alembic.config import Config

    config_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    if not config_path.is_file():
        raise RuntimeError("Migration files are missing; run from the source checkout")
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(path)
    try:
        config = Config(str(config_path))
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()
