"""HTTP surface of the agent: start a run to the human gate, then resume it with a decision."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.modules.agent.llm.base import LlmUnavailable
from app.modules.agent.schemas import HumanDecision, ProposalOut, RunOut, RunRequest
from app.modules.agent.service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


def get_agent_service(request: Request) -> AgentService:
    """The service is built once at startup (it owns the run checkpointer)."""
    svc: AgentService | None = getattr(request.app.state, "agent_service", None)
    if svc is None:
        raise LlmUnavailable("No LLM provider configured")
    return svc


Service = Annotated[AgentService, Depends(get_agent_service)]


@router.post("/runs")
async def start_run(body: RunRequest, svc: Service) -> ProposalOut:
    return await svc.start_run(body.sku, body.node)


@router.post("/runs/{thread_id}/resume")
async def resume_run(thread_id: str, body: HumanDecision, svc: Service) -> RunOut:
    return await svc.resume_run(thread_id, body)
