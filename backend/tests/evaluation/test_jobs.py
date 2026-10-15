from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.errors import Conflict
from app.modules.evaluation import jobs as jobs_module
from app.modules.evaluation.jobs import EvalJobs
from app.modules.evaluation.models import EvalRun
from app.modules.evaluation.service import get_run


async def test_started_run_is_running_then_finishes_with_results(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    jobs = EvalJobs(sessionmaker, get_settings())
    header = await jobs.start(live=False, repeat=1)
    assert header.finished_at is None
    assert header.mode == "offline"

    await jobs.drain()
    async with sessionmaker() as session:
        run = await get_run(session, header.id)
    assert run.finished_at is not None
    assert run.summary["cases"] == len(run.results) > 0
    assert run.summary["hard_violations"] == 0


async def test_second_start_while_one_is_unfinished_conflicts(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        session.add(EvalRun(scenario="1", mode="live", started_at=datetime.now(UTC)))
        await session.commit()
    with pytest.raises(Conflict):
        await EvalJobs(sessionmaker, get_settings()).start(live=False, repeat=1)


async def test_failed_run_is_closed_with_the_error(
    sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(jobs_module, "run_evaluation", boom)
    jobs = EvalJobs(sessionmaker, get_settings())
    header = await jobs.start(live=False, repeat=1)
    await jobs.drain()
    async with sessionmaker() as session:
        row = await session.get(EvalRun, header.id)
    assert row is not None and row.finished_at is not None
    assert row.summary == {"error": "RuntimeError: provider exploded"}


async def test_recover_closes_runs_a_restart_interrupted(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        session.add(EvalRun(scenario="1", mode="live", started_at=datetime.now(UTC)))
        await session.commit()
    await EvalJobs(sessionmaker, get_settings()).recover()
    async with sessionmaker() as session:
        row = await session.get(EvalRun, 1)
    assert row is not None and row.finished_at is not None
    assert row.summary == {"error": "interrupted by a restart"}
