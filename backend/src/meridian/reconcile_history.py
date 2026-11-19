"""Explicit private local report: python -m meridian.reconcile_history --help."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from meridian.application.history_reconciliation import history_reconciliation


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private read-only quantity reconciliation report")
    parser.add_argument(
        "--database", required=True, type=Path, help="Local SQLite evidence database"
    )
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args(argv)
    engine = None
    try:
        # mode=ro prevents implicit creation and WAL/configuration writes. A single
        # explicit read transaction pins the snapshot for all report queries.
        uri = args.database.resolve().as_uri() + "?mode=ro"
        engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            with Session(bind=connection) as db:
                report = history_reconciliation(db, account_id=args.account_id)
            connection.rollback()
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        # Third-party exceptions can include paths, SQL and financial bind values.
        print("reconciliation_failed: verify local evidence and account scope", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
