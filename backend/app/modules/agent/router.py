"""HTTP surface of the agent: start a run, poll it, then send the buyer's decision.

Every route needs a signed-in user; the decision records who made it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.agent import service
from app.modules.agent.llm.base import LlmUnavailable
from app.modules.agent.schemas import HumanDecision, RunOut, RunRequest, RunSummary
from app.modules.agent.service import AgentService
from app.modules.auth.deps import CurrentUser, current_user
from app.shared.enums import RunStatus

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(current_user)])


def get_agent_service(request: Request) -> AgentService:
    """The service is built once at startup (it owns the background run tasks)."""
    svc: AgentService | None = getattr(request.app.state, "agent_service", None)
    if svc is None:
        raise LlmUnavailable("No LLM provider configured")
    return svc


Service = Annotated[AgentService, Depends(get_agent_service)]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: RunRequest, svc: Service) -> RunOut:
    return await svc.start_run(body.sku, body.node)


@router.get("/runs")
async def list_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RunSummary]:
    return await service.list_runs(session, run_status, limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, svc: Service) -> RunOut:
    return await svc.get_run(run_id)


@router.post("/runs/{run_id}/decision")
async def decide(run_id: str, body: HumanDecision, svc: Service, user: CurrentUser) -> RunOut:
    return await svc.decide(run_id, body, user_id=user.id)
