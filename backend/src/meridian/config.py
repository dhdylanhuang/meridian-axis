"""Validated process configuration; secrets never enter application settings storage."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MERIDIAN_", extra="forbid")

    data_dir: Path = Path("private/runtime")
    broker_environment: Literal["demo", "live"] = "demo"
    broker_api_key: SecretStr | None = Field(default=None, repr=False)
    broker_api_secret: SecretStr | None = Field(default=None, repr=False)
    quote_interval_seconds: int = Field(default=60, ge=15, le=3600)
    intraday_retention_days: int = Field(default=90, ge=1, le=3650)
    max_import_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)

    @model_validator(mode="after")
    def paired_credentials(self) -> "Settings":
        if (self.broker_api_key is None) != (self.broker_api_secret is None):
            raise ValueError("Broker credentials must be configured together")
        for value in (self.broker_api_key, self.broker_api_secret):
            if value is not None and not value.get_secret_value().strip():
                raise ValueError("Broker credentials must not be empty")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir.resolve() / f"{self.broker_environment}.sqlite3"

    @property
    def broker_base_url(self) -> str:
        return f"https://{self.broker_environment}.trading212.com"
