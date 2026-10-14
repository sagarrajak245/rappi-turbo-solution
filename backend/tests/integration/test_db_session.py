from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import ForeignKey, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db import DbConfig, DbMode, UTCDateTime, create_engine, create_sessionmaker


class _Base(DeclarativeBase):
    pass


class _Parent(_Base):
    __tablename__ = "parent"
    id: Mapped[int] = mapped_column(primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(UTCDateTime())


class _Child(_Base):
    __tablename__ = "child"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("parent.id"))


@pytest.fixture
async def sessionmaker(tmp_path: Path):  # type: ignore[no-untyped-def]
    cfg = DbConfig(url=f"sqlite+aiosqlite:///{(tmp_path / 't.db').as_posix()}", mode=DbMode.SQLITE)
    engine = create_engine(cfg)
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    yield create_sessionmaker(engine)
    await engine.dispose()


async def test_sqlite_enforces_foreign_keys(sessionmaker) -> None:  # type: ignore[no-untyped-def]
    async with sessionmaker() as session:
        session.add(_Child(id=1, parent_id=999))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_datetimes_come_back_timezone_aware_in_utc(sessionmaker) -> None:  # type: ignore[no-untyped-def]
    ist = timezone(timedelta(hours=5, minutes=30))
    async with sessionmaker() as session:
        session.add(_Parent(id=1, seen_at=datetime(2026, 10, 14, 10, 0, tzinfo=ist)))
        await session.commit()
    async with sessionmaker() as session:
        seen_at = (await session.execute(select(_Parent.seen_at))).scalar_one()
    assert seen_at.tzinfo is not None
    assert seen_at == datetime(2026, 10, 14, 4, 30, tzinfo=UTC)


async def test_naive_datetimes_are_refused(sessionmaker) -> None:  # type: ignore[no-untyped-def]
    async with sessionmaker() as session:
        session.add(_Parent(id=2, seen_at=datetime(2026, 10, 14, 10, 0)))
        with pytest.raises(Exception, match="timezone"):
            await session.commit()
