import pytest

from meridian.application.imports import ImportStorageError
from meridian.cli import main

SYNTHETIC = (
    "Slice,Name,Invested value,Value,Result,Owned quantity,Dividends gained,"
    "Dividends cash,Dividends reinvested\n"
    "SYN,Synthetic holding,10,12,2,0.25,N/A,N/A,N/A\n"
    "Total,Synthetic group,10,12,2,-,3,1,1\n"
)


@pytest.fixture
def arguments(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_DATA_DIR", str(tmp_path / "runtime"))
    source = tmp_path / "synthetic.csv"
    source.write_text(SYNTHETIC, encoding="utf-8")
    return [str(source), "--currency", "GBP", "--observed-at", "2026-10-01T10:00:00Z"]


def test_preview_does_not_create_database_and_hides_values(arguments, tmp_path, capsys):
    assert main(["preview-holdings", *arguments]) == 0
    assert not (tmp_path / "runtime").exists()
    output = capsys.readouterr().out
    assert '"holding_rows": 1' in output
    assert "Synthetic holding" not in output
    assert "Synthetic group" not in output


def test_import_requires_initialized_database_and_deduplicates(arguments, capsys):
    assert main(["import-holdings", *arguments]) == 2
    assert "database_not_initialized" in capsys.readouterr().err
    assert main(["db-init"]) == 0
    assert main(["import-holdings", *arguments]) == 0
    assert main(["import-holdings", *arguments]) == 2
    output = capsys.readouterr()
    assert '"status": "duplicate"' in output.out
    assert "Synthetic holding" not in output.out + output.err


def test_naive_observation_time_rejected(arguments):
    arguments[-1] = "2026-10-01T10:00:00"
    with pytest.raises(SystemExit) as exc:
        main(["preview-holdings", *arguments])
    assert exc.value.code == 2


def test_bad_snapshot_import_is_a_safe_failure(arguments, capsys):
    assert main(["db-init"]) == 0
    arguments[arguments.index("GBP")] = "USD"
    assert main(["import-holdings", *arguments]) == 2
    output = capsys.readouterr()
    assert "Synthetic holding" not in output.out + output.err


def test_unavailable_import_log_returns_safe_failure(arguments, monkeypatch, capsys):
    assert main(["db-init"]) == 0

    def fail(*args, **kwargs):
        raise ImportStorageError("import_log_unavailable")

    monkeypatch.setattr("meridian.cli.import_holdings", fail)
    assert main(["import-holdings", *arguments]) == 2
    assert "import_log_unavailable" in capsys.readouterr().err
