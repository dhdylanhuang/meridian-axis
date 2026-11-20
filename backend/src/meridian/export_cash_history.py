"""Export a private local request for axis-reconciliation; no hosted calls."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from meridian.application.cash_history import cash_history_request


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private read-only Rust cash evidence export")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args(argv)
    engine = None
    try:
        uri = args.database.resolve().as_uri() + "?mode=ro"
        engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            with Session(bind=connection) as db:
                request = cash_history_request(db, account_id=args.account_id)
            connection.rollback()
        print(json.dumps(request, sort_keys=True))
        return 0
    except Exception:
        print("cash_history_export_failed", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
