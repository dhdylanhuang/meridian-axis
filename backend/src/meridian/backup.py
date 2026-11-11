"""Consistent SQLite backups and non-destructive, verified separate-path restores."""

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path


class BackupError(ValueError):
    """Safe diagnostic: never include source payloads or private paths."""


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def _controls(connection: sqlite3.Connection) -> dict:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise BackupError("database_integrity_failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise BackupError("database_foreign_key_failed")
    tables = sorted(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    )
    if "alembic_version" not in tables or "accounts" not in tables:
        raise BackupError("database_schema_unrecognised")
    revisions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    if len(revisions) != 1:
        raise BackupError("database_schema_unrecognised")
    counts = {}
    for table in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        counts[table] = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
    accounts = sorted(connection.execute("SELECT id, environment FROM accounts").fetchall())
    return {"schema_revision": revisions[0], "row_counts": counts, "accounts": accounts}


def manifest_path(backup_path: Path) -> Path:
    return backup_path.with_suffix(backup_path.suffix + ".manifest.json")


def _copy(reader: sqlite3.Connection, writer: sqlite3.Connection) -> None:
    deadline = time.monotonic() + 30

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() > deadline:
            raise BackupError("backup_timeout")

    reader.backup(writer, pages=256, progress=progress, sleep=0.05)


def create_backup(source: Path, destination: Path) -> dict:
    """Backup committed WAL state; refuse to replace any existing backup or manifest."""
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file():
        raise BackupError("source_database_missing")
    if source == destination:
        raise BackupError("backup_requires_separate_path")
    manifest = manifest_path(destination)
    if destination.exists() or manifest.exists():
        raise BackupError("backup_destination_exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against another backup racing this process.
    destination.touch(exist_ok=False)
    wrote_manifest = False
    try:
        with closing(_readonly(source)) as reader, closing(sqlite3.connect(destination)) as writer:
            _copy(reader, writer)
            # A backup should be self-contained, independent of WAL sidecars.
            writer.execute("PRAGMA journal_mode=DELETE")
            controls = _controls(writer)
        report = {
            "format_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "sha256": _digest(destination),
            **controls,
        }
        with manifest.open("x", encoding="utf-8") as stream:
            wrote_manifest = True
            json.dump(report, stream, sort_keys=True, indent=2)
            stream.write("\n")
        return report
    except BaseException:
        destination.unlink(missing_ok=True)
        if wrote_manifest:
            manifest.unlink(missing_ok=True)
        raise


def restore_backup(backup: Path, destination: Path, *, environment: str) -> dict:
    """Validate backup evidence, restore into a new file, then validate the copy."""
    backup, destination = backup.resolve(), destination.resolve()
    if not backup.is_file() or not manifest_path(backup).is_file():
        raise BackupError("backup_or_manifest_missing")
    if destination.exists():
        raise BackupError("restore_destination_exists")
    try:
        report = json.loads(manifest_path(backup).read_text(encoding="utf-8"))
        if report.get("format_version") != 1 or report.get("sha256") != _digest(backup):
            raise BackupError("backup_manifest_mismatch")
        with closing(_readonly(backup)) as reader:
            controls = _controls(reader)
        # JSON serialises tuples as lists, so normalise the comparison.
        if json.loads(json.dumps(controls)) != {key: report.get(key) for key in controls}:
            raise BackupError("backup_controls_mismatch")
        if any(account[1] != environment for account in controls["accounts"]):
            raise BackupError("backup_environment_mismatch")
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise BackupError("backup_manifest_invalid") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.touch(exist_ok=False)
    try:
        with closing(_readonly(backup)) as reader, closing(sqlite3.connect(destination)) as writer:
            _copy(reader, writer)
            writer.execute("PRAGMA journal_mode=DELETE")
            if _controls(writer) != controls:
                raise BackupError("restored_controls_mismatch")
        return report
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
