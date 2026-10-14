from collections.abc import Iterator

import pytest

from app.core import db
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never read the developer's real .env or shell overrides, and never share caches."""
    for var in ("DATABASE_URL", "DATABASE_URL_DIRECT", "REDIS_URL", "SETTINGS_FILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ENV_FILE", "")
    get_settings.cache_clear()
    db.reset_engine()
    yield
    get_settings.cache_clear()
    db.reset_engine()
