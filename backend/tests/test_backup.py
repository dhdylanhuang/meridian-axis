import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from meridian.backup import BackupError, create_backup, manifest_path, restore_backup
from meridian.cli import initialize_database, main
from meridian.config import Settings
from meridian.persistence.database import create_db_engine
from meridian.persistence.models import ImportRun, SourceRecord


@pytest.fixture
def database(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    initialize_database(settings)
    engine = create_db_engine(settings.database_path)
    # Keep a WAL-capable connection open to prove backup includes committed WAL data.
    with engine.connect() as keeper:
        with Session(engine) as session, session.begin():
            session.add(
                ImportRun(
                    id="synthetic-run",
                    account_id="demo-isa",
                    kind="synthetic",
                    status="succeeded",
                    content_hash="a" * 64,
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                )
            )
            session.flush()
            session.add(
                SourceRecord(
                    id="synthetic-evidence",
                    run_id="synthetic-run",
                    account_id="demo-isa",
                    kind="synthetic",
                    schema_version="synthetic/v1",
                    digest="b" * 64,
                    payload_json='{"quantity":"0.12345678901234567890123456789"}',
                    row_number=1,
                )
            )
        assert keeper.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"
        yield settings
    engine.dispose()


def test_backup_restore_includes_committed_wal_and_exact_source(database, tmp_path):
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    report = create_backup(database.database_path, backup)
    assert report["row_counts"]["source_records"] == 1
    assert report["schema_revision"] == "0004"
    restore_backup(backup, restored, environment="demo")
    with closing(sqlite3.connect(restored)) as connection:
        assert connection.execute("SELECT payload_json FROM source_records").fetchone()[0] == (
            '{"quantity":"0.12345678901234567890123456789"}'
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert database.database_path.is_file()


def test_refuses_overwrite_or_wrong_environment(database, tmp_path):
    backup = tmp_path / "backup.sqlite3"
    create_backup(database.database_path, backup)
    before = backup.read_bytes()
    with pytest.raises(BackupError, match="destination_exists"):
        create_backup(database.database_path, backup)
    assert backup.read_bytes() == before
    with pytest.raises(BackupError, match="destination_exists"):
        restore_backup(backup, database.database_path, environment="demo")
    wrong_environment = tmp_path / "must-not-exist.sqlite3"
    with pytest.raises(BackupError, match="environment_mismatch"):
        restore_backup(backup, wrong_environment, environment="live")
    assert not wrong_environment.exists()


@pytest.mark.parametrize("tamper", ["bytes", "manifest_controls", "invalid_manifest"])
def test_detects_corruption_before_restore(database, tmp_path, tamper):
    backup = tmp_path / "backup.sqlite3"
    create_backup(database.database_path, backup)
    if tamper == "bytes":
        with backup.open("ab") as stream:
            stream.write(b"corruption")
    elif tamper == "manifest_controls":
        manifest = json.loads(manifest_path(backup).read_text())
        manifest["row_counts"]["source_records"] = 999
        manifest_path(backup).write_text(json.dumps(manifest))
    else:
        manifest_path(backup).write_text("not JSON")
    destination = tmp_path / "must-not-exist.sqlite3"
    with pytest.raises(BackupError):
        restore_backup(backup, destination, environment="demo")
    assert not destination.exists()


def test_missing_source_is_not_created_and_failed_backup_removed(tmp_path):
    source = tmp_path / "missing.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    with pytest.raises(BackupError, match="source_database_missing"):
        create_backup(source, backup)
    assert not source.exists()
    source.write_bytes(b"not a database")
    with pytest.raises(sqlite3.DatabaseError):
        create_backup(source, backup)
    assert not backup.exists()
    assert not manifest_path(backup).exists()


def test_cli_bootstrap_upgrade_backup_and_separate_restore(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path / "runtime"))
    assert main(["db-init"]) == 0
    assert main(["db-init"]) == 0
    assert len(list((tmp_path / "runtime/backups").glob("*.sqlite3"))) == 1
    backup = tmp_path / "backup.sqlite3"
    assert main(["backup", str(backup)]) == 0
    restored = tmp_path / "restore.sqlite3"
    assert main(["restore", str(backup), str(restored)]) == 0
    assert main(["restore", str(backup), str(restored)]) == 2
    output = capsys.readouterr()
    assert "verified" in output.out
    assert str(tmp_path) not in output.out + output.err


def test_cli_invalid_credentials_never_print_values(monkeypatch, capsys):
    monkeypatch.setenv("MERIDIAN_BROKER_API_KEY", "synthetic-sensitive-value")
    monkeypatch.delenv("MERIDIAN_BROKER_API_SECRET", raising=False)
    assert main(["db-init"]) == 2
    assert "synthetic-sensitive-value" not in capsys.readouterr().err
