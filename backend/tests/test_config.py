from pathlib import Path

import pytest
from pydantic import ValidationError

from meridian.config import Settings


def test_demo_default_and_explicit_live_use_separate_paths(tmp_path):
    demo = Settings(data_dir=tmp_path, _env_file=None)
    live = Settings(data_dir=tmp_path, broker_environment="live", _env_file=None)
    assert demo.broker_base_url == "https://demo.trading212.com"
    assert live.broker_base_url == "https://live.trading212.com"
    assert demo.database_path != live.database_path
    assert demo.database_path.parent == tmp_path


def test_environment_loading_and_secret_repr(monkeypatch):
    monkeypatch.setenv("MERIDIAN_BROKER_API_KEY", "synthetic-key-never-real")
    monkeypatch.setenv("MERIDIAN_BROKER_API_SECRET", "synthetic-secret-never-real")
    settings = Settings()
    assert "synthetic-key" not in repr(settings)
    assert "synthetic-secret" not in repr(settings)
    assert "synthetic-secret" not in settings.model_dump_json()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"broker_environment": "https://attacker.invalid"},
        {"broker_api_key": "synthetic"},
        {"broker_api_key": "", "broker_api_secret": ""},
        {"quote_interval_seconds": 0},
        {"intraday_retention_days": -1},
    ],
)
def test_invalid_configuration_rejected(kwargs):
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_data_directory_must_be_a_path():
    assert Settings(data_dir="private/example").data_dir == Path("private/example")
