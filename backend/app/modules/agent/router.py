"""HTTP surface of the agent: start a run, poll it, then send the buyer's decision.

Every route needs a signed-in user; the decision records who made it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.modules.agent.llm.base import LlmUnavailable
from app.modules.agent.schemas import HumanDecision, RunOut, RunRequest
from app.modules.agent.service import AgentService
from app.modules.auth.deps import CurrentUser, current_user

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


@router.get("/runs/{run_id}")
async def get_run(run_id: str, svc: Service) -> RunOut:
    return await svc.get_run(run_id)


@router.post("/runs/{run_id}/decision")
async def decide(run_id: str, body: HumanDecision, svc: Service, user: CurrentUser) -> RunOut:
    return await svc.decide(run_id, body, user_id=user.id)
