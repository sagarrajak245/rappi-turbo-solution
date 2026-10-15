"""Evaluation runs: start one in the background, list stored runs and their per-case results."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_sessionmaker
from app.modules.auth.deps import require_role
from app.modules.evaluation import service
from app.modules.evaluation.jobs import EvalJobs
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


def get_jobs(request: Request) -> EvalJobs:
    jobs: EvalJobs = request.app.state.eval_jobs
    return jobs


Jobs = Annotated[EvalJobs, Depends(get_jobs)]


class StartEvalIn(BaseModel):
    live: bool = True  # the configured LLM providers; False uses the oracle (pipeline check only)
    repeat: int = Field(default=1, ge=1, le=3)


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartEvalIn, jobs: Jobs) -> EvalRunHeader:
    return await jobs.start(live=body.live, repeat=body.repeat)


@router.get("/runs")
async def list_runs(store: Store) -> list[EvalRunHeader]:
    async with store() as session:
        return await service.list_runs(session)


@router.get("/runs/{run_id}")
async def get_run(run_id: int, store: Store) -> EvalRunOut:
    async with store() as session:
        return await service.get_run(session, run_id)
