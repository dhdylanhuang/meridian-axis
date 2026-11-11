"""Local administrative commands; no broker calls or unauthenticated financial API."""

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from meridian.adapters.holdings_csv import HoldingsCSVError, parse_holdings_csv
from meridian.application.imports import ImportStorageError, ImportValidationError, import_holdings
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
    for command in ("preview-holdings", "import-holdings"):
        snapshot = commands.add_parser(command, help="Validate or store holdings snapshot evidence")
        snapshot.add_argument("source", type=Path)
        snapshot.add_argument("--currency", required=True)
        snapshot.add_argument("--observed-at", required=True, type=_observation_time)
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        if args.command == "db-init":
            initialize_database(settings)
        elif args.command == "backup":
            create_backup(settings.database_path, args.destination)
        elif args.command == "restore":
            restore_backup(args.backup, args.destination, environment=settings.broker_environment)
        else:
            with args.source.open("rb") as stream:
                content = stream.read(settings.max_import_bytes + 1)
            if args.command == "preview-holdings":
                snapshot = parse_holdings_csv(
                    content,
                    currency=args.currency,
                    observed_at=args.observed_at,
                    max_bytes=settings.max_import_bytes,
                )
                print(
                    json.dumps(
                        {
                            "status": "valid_snapshot_evidence",
                            "holding_rows": len(snapshot.holdings),
                            "control_rows": 1,
                            "economic_events_added": 0,
                        },
                        sort_keys=True,
                    )
                )
            else:
                if not settings.database_path.is_file():
                    raise BackupError("database_not_initialized")
                engine = create_db_engine(settings.database_path)
                try:
                    report = import_holdings(
                        engine,
                        account_id=f"{settings.broker_environment}-isa",
                        content=content,
                        currency=args.currency,
                        observed_at=args.observed_at,
                        max_bytes=settings.max_import_bytes,
                    )
                finally:
                    engine.dispose()
                print(
                    json.dumps(
                        {
                            "status": report.status,
                            "counts": report.counts,
                            "error_code": report.safe_error,
                        },
                        sort_keys=True,
                    )
                )
                if report.status != "succeeded":
                    return 2
    except ValidationError:
        print("configuration_invalid: check environment settings", file=sys.stderr)
        return 2
    except (BackupError, HoldingsCSVError, ImportValidationError, ImportStorageError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, SQLAlchemyError):
        # Third-party exception text can contain paths, bind values and financial payloads.
        print("storage_operation_failed: check paths, permissions and schema", file=sys.stderr)
        return 2
    print(f"{args.command}: verified")
    return 0


def _observation_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError
        return parsed.astimezone(UTC)
    except ValueError:
        raise argparse.ArgumentTypeError("Use an ISO 8601 observation time with timezone") from None


if __name__ == "__main__":
    raise SystemExit(main())
