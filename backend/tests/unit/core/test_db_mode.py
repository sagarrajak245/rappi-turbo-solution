import pytest

from app.core.config import REPO_ROOT, Settings
from app.core.db import DbMode, resolve_database


def _settings(**kwargs: str) -> Settings:
    return Settings(**kwargs)  # type: ignore[arg-type]


def test_no_url_falls_back_to_sqlite_file_under_repo() -> None:
    cfg = resolve_database(_settings())
    assert cfg.mode is DbMode.SQLITE
    assert cfg.url.startswith("sqlite+aiosqlite:///")
    assert cfg.url.endswith("backend/data/app.db")
    assert REPO_ROOT.as_posix() in cfg.url


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://", "postgresql+asyncpg://"])
def test_postgres_urls_are_normalised_to_asyncpg(scheme: str) -> None:
    cfg = resolve_database(_settings(database_url=f"{scheme}u:p@localhost:5432/rappi"))
    assert cfg.mode is DbMode.POSTGRES
    assert cfg.url == "postgresql+asyncpg://u:p@localhost:5432/rappi"
    assert cfg.connect_args == {}


def test_sslmode_is_translated_for_asyncpg() -> None:
    cfg = resolve_database(
        _settings(database_url="postgresql://u:p@db.example:5432/x?sslmode=require")
    )
    assert cfg.url == "postgresql+asyncpg://u:p@db.example:5432/x?ssl=require"


def test_transaction_pooler_disables_prepared_statement_caches() -> None:
    cfg = resolve_database(_settings(database_url="postgresql://u:p@pooler.supabase.com:6543/x"))
    assert cfg.connect_args == {"statement_cache_size": 0}
    assert "prepared_statement_cache_size=0" in cfg.url


def test_direct_url_is_used_for_migrations_when_set() -> None:
    settings = _settings(
        database_url="postgresql://u:p@pooler:6543/x",
        database_url_direct="postgresql://u:p@direct:5432/x",
    )
    assert "direct:5432" in resolve_database(settings, direct=True).url
    assert "pooler:6543" in resolve_database(settings).url


def test_direct_falls_back_to_main_url() -> None:
    settings = _settings(database_url="postgresql://u:p@main:5432/x")
    assert "main:5432" in resolve_database(settings, direct=True).url


def test_unsupported_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="mysql"):
        resolve_database(_settings(database_url="mysql://u:p@h/x"))
