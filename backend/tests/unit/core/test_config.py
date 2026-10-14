from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _write_yaml(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_repo_settings_yaml_is_loaded_by_default() -> None:
    settings = Settings()
    assert settings.planning.order_cycle_days == 7
    assert settings.planning.z == pytest.approx(1.65)
    assert settings.data_quality.snapshot_max_age_hours == 24


def test_yaml_values_override_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "SETTINGS_FILE", str(_write_yaml(tmp_path, "planning:\n  order_cycle_days: 9\n"))
    )
    assert Settings().planning.order_cycle_days == 9


def test_env_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "SETTINGS_FILE", str(_write_yaml(tmp_path, "planning:\n  order_cycle_days: 9\n"))
    )
    monkeypatch.setenv("PLANNING__ORDER_CYCLE_DAYS", "5")
    assert Settings().planning.order_cycle_days == 5


def test_missing_yaml_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SETTINGS_FILE", str(tmp_path / "does-not-exist.yaml"))
    settings = Settings()
    assert settings.planning.order_cycle_days == 7
    assert settings.database_url == ""


def test_service_level_without_z_value_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "SETTINGS_FILE", str(_write_yaml(tmp_path, "planning:\n  service_level: 0.97\n"))
    )
    with pytest.raises(ValidationError, match="service_level"):
        Settings()
