"""Application settings.

Precedence (highest first): environment variables > .env file > config/settings.yaml > defaults.
Nested values use a double underscore in env vars, e.g. ``PLANNING__ORDER_CYCLE_DAYS=5``.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import BaseModel, model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_FILE = REPO_ROOT / "config" / "settings.yaml"
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


class AppSection(BaseModel):
    name: str = "rappi-turbo"
    currency: str = "INR"
    branch: str = "Mumbai"


class DatabaseSection(BaseModel):
    sqlite_path: str = "backend/data/app.db"  # relative to the repo root


class LoggingSection(BaseModel):
    level: str = "INFO"
    json_format: bool = True


class PlanningSettings(BaseModel):
    order_cycle_days: int = 7
    service_level: float = 0.95
    z_table: dict[float, float] = {0.90: 1.28, 0.95: 1.65, 0.98: 2.05, 0.99: 2.33}
    sales_window_days: int = 28
    accept_tolerance_pct: float = 0.10
    max_cover_days: int = 21
    max_deviation_from_rec_pct: float = 0.50
    shelf_life_safety_days: int = 1

    @model_validator(mode="after")
    def _service_level_has_z(self) -> Self:
        if self.service_level not in self.z_table:
            raise ValueError(
                f"service_level {self.service_level} has no z value in z_table "
                f"(supported: {sorted(self.z_table)})"
            )
        return self

    @property
    def z(self) -> float:
        return self.z_table[self.service_level]


class DataQualitySettings(BaseModel):
    snapshot_max_age_hours: int = 24
    forecast_sales_gap_warn_pct: float = 0.25
    forecast_sales_gap_block_pct: float = 0.50
    # Defaults mirror settings.yaml so a missing file never switches injection detection off.
    injection_patterns: list[str] = [
        "ignore (all |any )?(previous|prior) instructions",
        "you are now",
        "system prompt",
        "approve (this|the) order",
    ]


class ErpSettings(BaseModel):
    price_tolerance_pct: float = 0.02
    eta_tolerance_days: int = 1
    max_replans: int = 1


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__", extra="ignore")

    app_env: str = "local"
    database_url: str = ""
    database_url_direct: str = ""
    redis_url: str = ""

    app: AppSection = AppSection()
    database: DatabaseSection = DatabaseSection()
    logging: LoggingSection = LoggingSection()
    planning: PlanningSettings = PlanningSettings()
    data_quality: DataQualitySettings = DataQualitySettings()
    erp: ErpSettings = ErpSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # SETTINGS_FILE / ENV_FILE let tests and deployments point elsewhere.
        # ENV_FILE="" disables the .env file entirely.
        yaml_file = Path(os.environ.get("SETTINGS_FILE") or DEFAULT_SETTINGS_FILE)
        env_file = os.environ.get("ENV_FILE", str(DEFAULT_ENV_FILE)) or None
        dotenv = DotEnvSettingsSource(settings_cls, env_file=env_file, env_nested_delimiter="__")
        yaml = YamlConfigSettingsSource(settings_cls, yaml_file=yaml_file)
        return init_settings, env_settings, dotenv, yaml


@lru_cache
def get_settings() -> Settings:
    return Settings()
