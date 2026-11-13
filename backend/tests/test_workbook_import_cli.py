"""Synthetic CLI checks for preview defaults, scoped acceptance and safe diagnostics."""

import json
from dataclasses import asdict

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_workbook_baseline import layout, workbook

from meridian.cli import initialize_database
from meridian.config import Settings
from meridian.persistence.database import create_db_engine
from meridian.persistence.models import SourceRecord
from meridian.workbook_import_cli import main, read_layout


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("MERIDIAN_BROKER_ENVIRONMENT", "demo")
    source = tmp_path / "private-test-source.xlsx"
    source.write_bytes(workbook())
    mapping = tmp_path / "private-layout.json"
    mapping.write_text(json.dumps(asdict(layout()), default=str))
    return source, mapping


def test_default_preview_has_no_database_side_effect_and_output_has_no_private_data(inputs, capsys):
    source, mapping = inputs
    before = source.read_bytes()
    assert main([str(source), "--layout", str(mapping)]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result == {
        "economic_events_added": 0,
        "incomplete_observations": 1,
        "invested_controls_reconciled": 6,
        "observations": 6,
        "status": "valid_baseline_evidence",
        "unknown_dates": 1,
    }
    assert output.err == ""
    assert "private" not in output.out
    assert "100.123" not in output.out
    assert not Settings().database_path.exists()
    assert source.read_bytes() == before


def test_explicit_import_requires_initialized_database_then_deduplicates(inputs, capsys):
    source, mapping = inputs
    args = [str(source), "--layout", str(mapping), "--import"]
    assert main(args) == 2
    assert capsys.readouterr().err.strip() == "database_not_initialized"
    initialize_database(Settings())
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "succeeded"
    assert main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "duplicate"
    engine = create_db_engine(Settings().database_path)
    try:
        with Session(engine) as session:
            assert len(session.scalars(select(SourceRecord)).all()) == 6
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "content",
    [
        b'{"sheet":"x","sheet":"y","observations":[]}',
        b'{"sheet":"x","observations":[],"unknown":"secret"}',
        b'{"sheet":"x","observations":[{"groups":[],"observed_on":"private-date"}]}',
        b"private malformed layout",
    ],
)
def test_layout_errors_have_stable_safe_code(content):
    with pytest.raises(ValueError, match="^invalid_workbook_layout$"):
        read_layout(content)


def test_missing_files_emit_safe_error_without_paths(inputs, capsys):
    source, mapping = inputs
    source.unlink()
    assert main([str(source), "--layout", str(mapping)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err.strip() == "storage_operation_failed"
