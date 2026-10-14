"""Database fixtures for integration tests.

SQLite (a temp file) by default. Set TEST_DATABASE_URL to a disposable local Postgres to run the
same tests there, e.g. postgresql://postgres:postgres@localhost:5433/test. Tables are created
before and dropped after each test, so never point it at a database you care about.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import Settings
from app.core.db import Base, DbConfig, DbMode, create_engine, create_sessionmaker, resolve_database


def _test_db_config(tmp_path: Path) -> DbConfig:
    url = os.environ.get("TEST_DATABASE_URL", "")
    if url:
        return resolve_database(Settings(database_url=url))
    path = (tmp_path / "test.db").as_posix()
    return DbConfig(url=f"sqlite+aiosqlite:///{path}", mode=DbMode.SQLITE)


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(_test_db_config(tmp_path))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return create_sessionmaker(engine)


@pytest.fixture
async def session(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as s:
        yield s
