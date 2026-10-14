import pytest

from app.core.config import Settings
from app.core.db import resolve_database
from app.seed.guard import RemoteSeedRefused, ensure_seed_target


@pytest.mark.parametrize(
    "url",
    [
        "",  # SQLite fallback
        "postgresql://postgres:pw@localhost:5432/app",
        "postgresql://postgres:pw@127.0.0.1:5433/app",
        "postgresql://postgres:pw@postgres:5432/app",  # docker compose service name
    ],
)
def test_local_targets_are_allowed(url: str) -> None:
    ensure_seed_target(resolve_database(Settings(database_url=url)), allow_remote=False)


def test_remote_target_is_refused_without_confirmation() -> None:
    cfg = resolve_database(
        Settings(
            database_url="postgresql://u:pw@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
        )
    )
    with pytest.raises(RemoteSeedRefused) as exc:
        ensure_seed_target(cfg, allow_remote=False)
    assert "aws-0-ap-south-1.pooler.supabase.com" in str(exc.value)
    assert "pw" not in str(exc.value)  # never echo credentials


def test_remote_target_is_allowed_when_confirmed() -> None:
    cfg = resolve_database(Settings(database_url="postgresql://u:pw@db.example.com:5432/postgres"))
    ensure_seed_target(cfg, allow_remote=True)
