"""Prepare the private funding input for the Rust daily-session preflight."""

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from meridian.adapters.broker_evidence import instant
from meridian.application.performance_evidence import MAX_REQUEST_BYTES, performance_input


def session_funding(db, start_at, end_at, as_of):
    """Retain boundary events and only the coverage the export can support."""
    start, end, cutoff = map(instant, (start_at, end_at, as_of))
    if not start < end <= cutoff:
        raise ValueError("session_funding_dates_invalid")
    request = performance_input(
        db, {"days": [], "as_of": cutoff.isoformat(), "start_date": start.date().isoformat()}
    )
    events = [row for row in request["events"] if start <= instant(row["at"]) <= end]
    return limited_funding(request, start, end, events)


def limited_funding(request, start, end, events):
    coverage = request["coverage"]
    if coverage is not None:
        first = max(start, instant(coverage["start_at"]))
        last = min(end, instant(coverage["end_at"]))
        coverage = (
            coverage | {"start_at": first.isoformat(), "end_at": last.isoformat()}
            if first < last
            else None
        )
    return {"coverage": coverage, "events": events}


def write_funding_file(output: Path, evidence):
    payload = json.dumps(evidence, separators=(",", ":"), ensure_ascii=False).encode()
    if len(payload) > MAX_REQUEST_BYTES or len(evidence["events"]) > 1024:
        raise ValueError("session_funding_input_limit")
    # Commit only a complete, mode-0600 file and leave any existing file intact.
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        temporary = Path(directory) / "funding.json"
        with os.fdopen(
            os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as stream:
            stream.write(payload)
        os.link(temporary, output)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only shared ISA funding evidence export")
    parser.add_argument(
        "--database", required=True, type=Path, help="Local SQLite evidence database"
    )
    parser.add_argument("--start-at", required=True, help="Opening valuation instant")
    parser.add_argument("--end-at", required=True, help="Closing valuation instant")
    parser.add_argument("--as-of", required=True, help="Funding evidence review cutoff")
    parser.add_argument("--output", required=True, type=Path, help="New private JSON path")
    args = parser.parse_args(argv)
    engine = None
    try:
        uri = args.database.resolve().as_uri() + "?mode=ro"
        engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN")
            with Session(bind=connection) as db:
                evidence = session_funding(db, args.start_at, args.end_at, args.as_of)
            connection.rollback()
        write_funding_file(args.output, evidence)
    except Exception:
        print("session_funding_export_failed", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()
    print(
        json.dumps(
            {
                "funding_window_available": evidence["coverage"] is not None,
                "events_exported": len(evidence["events"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
