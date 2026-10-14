from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.modules.evaluation import repository as repo
from app.modules.evaluation.models import EvalRun
from app.modules.evaluation.schemas import EvalResultOut, EvalRunHeader, EvalRunOut


def _header(row: EvalRun) -> EvalRunHeader:
    return EvalRunHeader(
        id=row.id,
        scenario=row.scenario,
        mode=row.mode,
        started_at=row.started_at,
        finished_at=row.finished_at,
        summary=row.summary or {},
    )


async def list_runs(session: AsyncSession, limit: int = 50) -> list[EvalRunHeader]:
    return [_header(r) for r in await repo.list_runs(session, limit)]


async def get_run(session: AsyncSession, run_id: int) -> EvalRunOut:
    row = await repo.get_run(session, run_id)
    if row is None:
        raise NotFound(f"Unknown evaluation run {run_id}")
    results = [EvalResultOut.model_validate(r) for r in await repo.list_results(session, run_id)]
    return EvalRunOut(**_header(row).model_dump(), results=results)
