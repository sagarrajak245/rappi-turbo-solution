from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.evaluation.models import EvalResult, EvalRun


async def list_runs(session: AsyncSession, limit: int) -> Sequence[EvalRun]:
    rows = await session.scalars(select(EvalRun).order_by(EvalRun.id.desc()).limit(limit))
    return rows.all()


async def get_run(session: AsyncSession, run_id: int) -> EvalRun | None:
    return await session.get(EvalRun, run_id)


async def list_results(session: AsyncSession, run_id: int) -> Sequence[EvalResult]:
    rows = await session.scalars(
        select(EvalResult).where(EvalResult.eval_run_id == run_id).order_by(EvalResult.id)
    )
    return rows.all()
