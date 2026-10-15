"""Evaluation runs started from the API: one at a time, in the background, visible while running.

The row is created up front with no `finished_at`, so the page can show the run as running; the
background task completes it with the summary, or closes it with the error. A restart kills the
task, so `recover` closes any run left open.
"""

import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import Settings
from app.core.db import Base, DbConfig, DbMode, create_engine, create_sessionmaker
from app.core.errors import Conflict
from app.modules.evaluation.models import EvalRun
from app.modules.evaluation.runner import run_evaluation
from app.modules.evaluation.schemas import EvalRunHeader
from app.modules.evaluation.service import header

logger = logging.getLogger(__name__)


@asynccontextmanager
async def scratch_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A throwaway SQLite database for the scenario seed, so the real one is never touched."""
    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite+aiosqlite:///{(Path(tmp) / 'eval.db').as_posix()}"
        engine = create_engine(DbConfig(url=url, mode=DbMode.SQLITE))
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            yield create_sessionmaker(engine)
        finally:
            await engine.dispose()


class EvalJobs:
    def __init__(
        self,
        store_sm: async_sessionmaker[AsyncSession],
        settings: Settings,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self._store = store_sm
        self._settings = settings
        self._http = http
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self, *, live: bool, repeat: int) -> EvalRunHeader:
        async with self._lock, self._store() as session:
            running = await session.scalar(
                select(EvalRun.id).where(EvalRun.finished_at.is_(None)).limit(1)
            )
            if running is not None:
                raise Conflict(f"Evaluation run {running} is still running")
            row = EvalRun(
                scenario="1", mode="live" if live else "offline", started_at=datetime.now(UTC)
            )
            session.add(row)
            await session.commit()
            out = header(row)
        task = asyncio.create_task(self._execute(out.id, live, repeat))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return out

    async def _execute(self, run_id: int, live: bool, repeat: int) -> None:
        try:
            async with scratch_sessionmaker() as work_sm:
                await run_evaluation(
                    work_sm,
                    self._store,
                    self._settings,
                    live=live,
                    repeat=repeat,
                    http=self._http,
                    run_id=run_id,
                )
        except Exception as exc:  # any failure must close the run, or the button stays locked
            logger.exception("evaluation run %s failed", run_id)
            try:
                await self._close(run_id, f"{type(exc).__name__}: {exc}")
            except Exception:  # store down too: recover() closes it on the next start
                logger.exception("could not close evaluation run %s", run_id)

    async def _close(self, run_id: int, error: str) -> None:
        async with self._store() as session:
            row = await session.get(EvalRun, run_id)
            if row is not None and row.finished_at is None:
                row.finished_at = datetime.now(UTC)
                row.summary = {"error": error}
                await session.commit()

    async def recover(self) -> None:
        async with self._store() as session:
            rows = await session.scalars(select(EvalRun).where(EvalRun.finished_at.is_(None)))
            for row in rows.all():
                row.finished_at = datetime.now(UTC)
                row.summary = {"error": "interrupted by a restart"}
            await session.commit()

    async def drain(self) -> None:
        """Wait for the running tasks (tests, shutdown)."""
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        await self.drain()
