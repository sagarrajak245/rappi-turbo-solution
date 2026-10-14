import pytest


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never read the developer's real .env or shell overrides."""
    for var in ("DATABASE_URL", "DATABASE_URL_DIRECT", "REDIS_URL", "SETTINGS_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENV_FILE", "")
