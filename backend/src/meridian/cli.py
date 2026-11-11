"""Local administrative commands; no broker calls or unauthenticated financial API."""

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from meridian.backup import BackupError, create_backup, restore_backup
from meridian.config import Settings
from meridian.persistence.database import create_db_engine, upgrade_database
from meridian.persistence.models import Account, AuditRecord


def initialize_database(settings: Settings) -> None:
    path = settings.database_path
    if path.exists():
        # Upgrades are maintenance operations and preserve an independent prior copy.
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        backup = path.parent / "backups" / f"before-upgrade-{stamp}-{uuid4().hex[:8]}.sqlite3"
        create_backup(path, backup)
    upgrade_database(path)
    engine = create_db_engine(path)
    try:
        with Session(engine) as session, session.begin():
            accounts = session.scalars(select(Account)).all()
            account_id = f"{settings.broker_environment}-isa"
            if accounts:
                if len(accounts) != 1 or (
                    accounts[0].id,
                    accounts[0].environment,
                    accounts[0].currency,
                ) != (account_id, settings.broker_environment, "GBP"):
                    raise BackupError("database_account_scope_mismatch")
                return
            session.add(
                Account(id=account_id, environment=settings.broker_environment, currency="GBP")
            )
            session.flush()
            session.add(
                AuditRecord(
                    id=uuid4().hex,
                    occurred_at=datetime.now(UTC),
                    actor="local-admin",
                    action="account_initialized",
                    entity_type="account",
                    entity_id=account_id,
                    details_json='{"currency":"GBP","wrapper":"isa"}',
                )
            )
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Great Dyke Meridian local administration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "db-init", help="Apply reviewed migrations and initialise the configured ISA"
    )
    backup = commands.add_parser("backup", help="Online backup with verification manifest")
    backup.add_argument("destination", type=Path)
    restore = commands.add_parser("restore", help="Verify and restore to a new separate path")
    restore.add_argument("backup", type=Path)
    restore.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        if args.command == "db-init":
            initialize_database(settings)
        elif args.command == "backup":
            create_backup(settings.database_path, args.destination)
        else:
            restore_backup(args.backup, args.destination, environment=settings.broker_environment)
    except ValidationError:
        print("configuration_invalid: check environment settings", file=sys.stderr)
        return 2
    except BackupError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, SQLAlchemyError):
        # Third-party exception text can contain paths, bind values and financial payloads.
        print("storage_operation_failed: check paths, permissions and schema", file=sys.stderr)
        return 2
    print(f"{args.command}: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
