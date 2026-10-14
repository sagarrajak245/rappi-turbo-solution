"""Public surface of the agent module: start a run to the human gate, then resume it.

The graph is compiled once per service with an in-memory checkpointer (thread_id = run id).
A durable Postgres/SQLite checkpointer and the agent_runs table arrive in Session B2.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import Conflict, NotFound
from app.modules.agent.graph import GraphDeps, build_graph
from app.modules.agent.llm.base import LlmCallRecord, LlmClient
from app.modules.agent.schemas import DecisionOut, HumanDecision, ProposalOut, RunOut
from app.modules.agent.state import AgentState
from app.modules.planning.schemas import (
    CalcResult,
    Flag,
    InboundPo,
    PlanningInput,
    ResolutionOption,
    Violation,
)
from app.modules.validation.schemas import (
    ProposedDecision,
    SoftBreach,
    SoftOverride,
    ValidationResult,
)
from app.shared.enums import ConstraintCode, FlagCode, FlagSeverity, Outcome, Verdict

# Types the checkpointer may revive from state. Explicit, because LangGraph will refuse
# unregistered types in a future version (and warns on every load until then).
_STATE_TYPES: tuple[type, ...] = (
    LlmCallRecord,
    DecisionOut,
    ProposalOut,
    RunOut,
    PlanningInput,
    InboundPo,
    Flag,
    Violation,
    ResolutionOption,
    CalcResult,
    ProposedDecision,
    SoftOverride,
    SoftBreach,
    ValidationResult,
    Verdict,
    Outcome,
    FlagSeverity,
    FlagCode,
    ConstraintCode,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AgentService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        decide_llm: LlmClient,
        review_llm: LlmClient,
        settings: Settings,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        deps = GraphDeps(sessionmaker, decide_llm, review_llm, settings)
        self._graph = build_graph(
            deps, InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=_STATE_TYPES))
        )
        self._clock = clock

    @staticmethod
    def _config(thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}}

    async def start_run(self, sku: str, node: str) -> ProposalOut:
        """Run the graph for one SKU x node until it stops at the human gate."""
        thread_id = uuid.uuid4().hex
        now = self._clock()
        state: AgentState = {
            "thread_id": thread_id,
            "sku": sku,
            "node": node,
            "today": now.date(),
            "now": now,
        }
        config = self._config(thread_id)
        await self._graph.ainvoke(state, config)
        snapshot = await self._graph.aget_state(config)
        proposal: ProposalOut = snapshot.values["proposal"]
        return proposal

    async def resume_run(self, thread_id: str, decision: HumanDecision) -> RunOut:
        """Feed the buyer's decision into the waiting human gate."""
        config = self._config(thread_id)
        snapshot = await self._graph.aget_state(config)
        if not snapshot.values:
            raise NotFound(f"Run {thread_id} not found", {"thread_id": thread_id})
        if not snapshot.next:
            raise Conflict(
                f"Run {thread_id} is not waiting for a decision", {"thread_id": thread_id}
            )
        await self._graph.ainvoke(Command(resume=decision.model_dump(mode="json")), config)
        run: RunOut = (await self._graph.aget_state(config)).values["run"]
        return run
