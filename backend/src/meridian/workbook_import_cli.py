"""Private local Excel baseline preview/import with safe, value-free output."""

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from meridian.adapters.workbook_baseline import (
    MAX_BYTES,
    GroupCells,
    ObservationCells,
    WorkbookBaselineError,
    WorkbookBaselineLayout,
    parse_workbook_baseline,
)
from meridian.application.imports import ImportStorageError, ImportValidationError
from meridian.application.workbook_import import import_workbook_baseline
from meridian.config import Settings
from meridian.persistence.database import create_db_engine

MAX_LAYOUT_BYTES = 256 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def read_layout(content: bytes) -> WorkbookBaselineLayout:
    """Load explicit private cell mapping metadata, rejecting ambiguous fields."""
    try:
        if len(content) > MAX_LAYOUT_BYTES:
            raise ValueError
        document = json.loads(content, object_pairs_hook=_unique_object)
        if set(document) != {"sheet", "observations"}:
            raise ValueError
        if not isinstance(document["observations"], list):
            raise ValueError
        observations = []
        for item in document["observations"]:
            item = dict(item)
            groups = tuple(GroupCells(**group) for group in item.pop("groups"))
            observed_on = item.get("observed_on")
            if observed_on is not None:
                item["observed_on"] = date.fromisoformat(observed_on)
            observations.append(ObservationCells(groups=groups, **item))
        return WorkbookBaselineLayout(document["sheet"], tuple(observations))
    except Exception:
        raise WorkbookBaselineError("invalid_workbook_layout") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Preview or import private Excel baseline evidence"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--layout", required=True, type=Path, help="Private JSON cell mapping")
    parser.add_argument("--import", dest="accept", action="store_true", help="Commit evidence")
    args = parser.parse_args(argv)
    try:
        settings = Settings()
        with args.layout.open("rb") as stream:
            layout = read_layout(stream.read(MAX_LAYOUT_BYTES + 1))
        with args.source.open("rb") as stream:
            content = stream.read(min(settings.max_import_bytes, MAX_BYTES) + 1)
        if len(content) > settings.max_import_bytes:
            raise WorkbookBaselineError("file_too_large")
        if args.accept:
            if not settings.database_path.is_file():
                raise WorkbookBaselineError("database_not_initialized")
            engine = create_db_engine(settings.database_path)
            try:
                report = import_workbook_baseline(
                    engine,
                    account_id=f"{settings.broker_environment}-isa",
                    content=content,
                    layout=layout,
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
            return 0 if report.status == "succeeded" else 2
        baseline = parse_workbook_baseline(content, layout=layout)
        print(
            json.dumps(
                {
                    "status": "valid_baseline_evidence",
                    "observations": len(baseline.observations),
                    "economic_events_added": 0,
                    "unknown_dates": sum(
                        row["date_precision"] == "unknown" for row in baseline.observations
                    ),
                    "incomplete_observations": sum(
                        bool(row["missing_groups"]) for row in baseline.observations
                    ),
                    "invested_controls_reconciled": sum(
                        row["invested_reconciled"] for row in baseline.observations
                    ),
                },
                sort_keys=True,
            )
        )
        return 0
    except ValidationError:
        print("configuration_invalid", file=sys.stderr)
    except (WorkbookBaselineError, ImportValidationError, ImportStorageError) as exc:
        print(str(exc), file=sys.stderr)
    except (OSError, sqlite3.Error, SQLAlchemyError):
        print("storage_operation_failed", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
