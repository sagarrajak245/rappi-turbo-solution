"""Read side of the evaluation runner: stored runs and their per-case results."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_sessionmaker
from app.modules.auth.deps import require_role
from app.modules.evaluation import service
from app.modules.evaluation.schemas import EvalRunHeader, EvalRunOut
from app.shared.enums import UserRole

router = APIRouter(
    prefix="/evaluation",
    tags=["evaluation"],
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


def get_store() -> async_sessionmaker[AsyncSession]:
    return get_sessionmaker()


Store = Annotated[async_sessionmaker[AsyncSession], Depends(get_store)]


@router.get("/runs")
async def list_runs(store: Store) -> list[EvalRunHeader]:
    async with store() as session:
        return await service.list_runs(session)


@router.get("/runs/{run_id}")
async def get_run(run_id: int, store: Store) -> EvalRunOut:
    async with store() as session:
        return await service.get_run(session, run_id)
