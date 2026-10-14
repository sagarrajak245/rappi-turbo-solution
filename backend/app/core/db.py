"""Database engine, sessions and the declarative Base.

Only DATABASE_URL decides the mode (KB D6):
  * empty            -> SQLite file (no Docker needed)
  * postgres URL     -> asyncpg (local Docker Postgres or Supabase)
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import DateTime, Dialect, MetaData, event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.core.config import REPO_ROOT, Settings, get_settings

# Stable constraint names so Alembic migrations are identical on SQLite and Postgres.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SUPABASE_TRANSACTION_POOLER_PORT = 6543


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetimes on every backend.

    SQLite has no timezone support and hands back naive values; this normalises
    everything to UTC and refuses naive input so comparisons never mix the two.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime refused: pass a timezone-aware value")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class DbMode(StrEnum):
    POSTGRES = "postgres"
    SQLITE = "sqlite"


@dataclass(frozen=True)
class DbConfig:
    url: str
    mode: DbMode
    connect_args: dict[str, Any] = field(default_factory=dict)


def resolve_database(settings: Settings, *, direct: bool = False) -> DbConfig:
    """Turn settings into an async SQLAlchemy URL. ``direct`` = the URL Alembic should use."""
    raw = (settings.database_url_direct if direct else "") or settings.database_url
    if not raw:
        path = REPO_ROOT / settings.database.sqlite_path
        return DbConfig(url=f"sqlite+aiosqlite:///{path.as_posix()}", mode=DbMode.SQLITE)

    scheme, _, rest = raw.partition("://")
    if scheme.startswith("sqlite"):
        # Not via urlsplit: it would drop the empty host in sqlite:///path.
        return DbConfig(url=f"sqlite+aiosqlite://{rest}", mode=DbMode.SQLITE)
    parts = urlsplit(raw)
    if scheme not in ("postgres", "postgresql", "postgresql+asyncpg"):
        raise ValueError(f"unsupported database scheme {scheme!r}; use postgres or sqlite")

    # asyncpg spells libpq's sslmode as ssl.
    query = [("ssl" if k == "sslmode" else k, v) for k, v in parse_qsl(parts.query)]
    connect_args: dict[str, Any] = {}
    if parts.port == SUPABASE_TRANSACTION_POOLER_PORT:
        # PgBouncer in transaction mode cannot keep prepared statements between transactions.
        query.append(("prepared_statement_cache_size", "0"))
        connect_args["statement_cache_size"] = 0
    url = urlunsplit(parts._replace(scheme="postgresql+asyncpg", query=urlencode(query)))
    return DbConfig(url=url, mode=DbMode.POSTGRES, connect_args=connect_args)


def create_engine(cfg: DbConfig) -> AsyncEngine:
    engine = _create_async_engine(cfg.url, connect_args=cfg.connect_args, pool_pre_ping=True)
    if cfg.mode is DbMode.SQLITE:

        @event.listens_for(engine.sync_engine, "connect")
        def _enable_foreign_keys(dbapi_conn: Any, _: Any) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


# --- process-wide engine (created lazily from settings) -------------------------------------

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        cfg = resolve_database(get_settings())
        if cfg.mode is DbMode.SQLITE and cfg.url.startswith("sqlite+aiosqlite:///"):
            Path(cfg.url.removeprefix("sqlite+aiosqlite:///")).parent.mkdir(
                parents=True, exist_ok=True
            )
        _engine = create_engine(cfg)
        _sessionmaker = create_sessionmaker(_engine)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessionmaker = None, None


def reset_engine() -> None:
    """Forget the cached engine (tests). Prefer dispose_engine() inside an event loop."""
    global _engine, _sessionmaker
    _engine, _sessionmaker = None, None
