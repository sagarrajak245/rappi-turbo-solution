"""Public surface of the agent module: a run is a persisted record (KB §3.2).

start_run inserts a `running` row and decides in a background task under a whole-run deadline;
the proposal then waits in the row for the buyer. decide() executes an approval in the ERP,
reading the re-plan count and the ERP's changed terms from the row, never from the client.
Nothing before the gate has side effects, so recover() simply re-runs rows left `running`.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import Conflict, NotFound
from app.modules.agent import repository as repo
from app.modules.agent.graph import GraphDeps, build_graph, human_verdict, validation_feedback
from app.modules.agent.llm.base import LlmClient
from app.modules.agent.models import AgentRun
from app.modules.agent.schemas import (
    HumanAction,
    HumanDecision,
    ProposalOut,
    RunOut,
    RunSummary,
)
from app.modules.agent.state import AgentState
from app.modules.erp_mock import service as erp
from app.modules.execution import service as execution
from app.modules.execution.schemas import ApprovedOrder, ExecutionResult, ExecutionStatus
from app.modules.memory import service as memory
from app.modules.planning import service as planning
from app.modules.planning.schemas import PlanningInput
from app.modules.validation import service as validation
from app.modules.validation.schemas import ProposedDecision
from app.shared.enums import Outcome, RunStatus

logger = logging.getLogger(__name__)

_EXECUTION_TO_RUN = {
    ExecutionStatus.COMPLETED: RunStatus.COMPLETED,
    ExecutionStatus.ESCALATED: RunStatus.ESCALATED,
    ExecutionStatus.NEEDS_HUMAN: RunStatus.NEEDS_HUMAN,
}


_NOTIFY_AFTER_DECISION = frozenset(_EXECUTION_TO_RUN.values())


@dataclass
class _Progress:
    erp_touched: bool = False  # the ERP may hold a PO from here on


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _out(row: AgentRun) -> RunOut:
    return RunOut(
        id=row.id,
        sku=row.sku,
        node=row.node_code,
        status=row.status,
        proposal=ProposalOut.model_validate(row.proposal) if row.proposal else None,
        execution=ExecutionResult.model_validate(row.execution) if row.execution else None,
        replans_done=row.replans_done,
        error=row.error,
    )


def summarize(row: AgentRun) -> RunSummary:
    p = row.proposal or {}
    reasons = p.get("reasons") or []
    return RunSummary(
        id=row.id,
        sku=row.sku,
        node=row.node_code,
        status=row.status,
        verdict=p.get("verdict"),
        qty=p.get("qty"),
        rec_qty=p.get("rec_qty"),
        outcome=p.get("outcome"),
        reason=reasons[0] if reasons else None,
        error=row.error,
        decided_by=row.decided_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def list_runs(
    session: AsyncSession, status: RunStatus | None, limit: int
) -> list[RunSummary]:
    """Newest first. A plain read: needs no LLM, so it lives outside AgentService."""
    return [summarize(r) for r in await repo.list_runs(session, status, limit)]


def _with_erp_terms(inp: PlanningInput, row: AgentRun) -> PlanningInput:
    """Planning input as the supplier now quotes it, after a re-plan."""
    update: dict[str, object] = {}
    if row.unit_price_override is not None:
        update["unit_cost_inr"] = row.unit_price_override
    if row.case_pack_override is not None:
        update["case_pack"] = row.case_pack_override
    return inp.model_copy(update=update) if update else inp


class AgentService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        decide_llm: LlmClient,
        review_llm: LlmClient,
        settings: Settings,
        clock: Callable[[], datetime] = _utcnow,
        notify: Callable[[str, str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._notify = notify  # (run_id, kind, message); injected so the agent stays decoupled
        self._sm = sessionmaker
        self._graph = build_graph(GraphDeps(sessionmaker, decide_llm, review_llm, settings))
        self._s = settings
        self._clock = clock
        self._tasks: set[asyncio.Task[None]] = set()  # in-process worker; strong refs

    # ---- deciding (background) ------------------------------------------------------------

    async def start_run(self, sku: str, node: str) -> RunOut:
        """Persist a `running` run and decide in the background; poll get_run for the result."""
        now = self._clock()
        row = AgentRun(
            id=uuid.uuid4().hex,
            sku=sku,
            node_code=node,
            status=RunStatus.RUNNING,
            replans_done=0,
            created_at=now,
            updated_at=now,
        )
        async with self._sm() as session:
            session.add(row)
            await session.commit()
            out = _out(row)
        self._schedule(out.id, sku, node)
        return out

    async def propose(self, run_id: str, sku: str, node: str) -> tuple[ProposalOut, AgentState]:
        """Run the graph to its proposal. No side effects, so it is safe to re-run."""
        now = self._clock()
        state: AgentState = {
            "thread_id": run_id,
            "sku": sku,
            "node": node,
            "today": now.date(),
            "now": now,
        }
        final: AgentState = await self._graph.ainvoke(state)  # type: ignore[assignment]
        return final["proposal"], final

    def _schedule(self, run_id: str, sku: str, node: str) -> None:
        task = asyncio.create_task(self._decide_in_background(run_id, sku, node))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _decide_in_background(self, run_id: str, sku: str, node: str) -> None:
        try:
            async with asyncio.timeout(self._s.llm.run_deadline_s):
                proposal, state = await self.propose(run_id, sku, node)
        except asyncio.CancelledError:
            raise  # shutdown: the row stays `running` and recover() re-runs it
        except TimeoutError:
            await self._fail(run_id, f"run exceeded its {self._s.llm.run_deadline_s}s deadline")
            return
        except Exception as exc:
            logger.exception("agent run failed", extra={"run_id": run_id})
            await self._fail(run_id, f"{type(exc).__name__}: {exc}")
            return
        async with self._sm() as session:
            now = self._clock()
            written = await repo.update_run(
                session,
                run_id,
                now,
                expected=RunStatus.RUNNING,  # another worker may have finished it meanwhile
                status=RunStatus.AWAITING_APPROVAL,
                proposal=proposal.model_dump(mode="json"),
                error=None,
            )
            if written:
                repo.add_llm_calls(session, run_id, state.get("llm_records", []), now)
                await memory.mark_applied(session, proposal.lessons_applied, now)
            await session.commit()
        if written:
            await self._tell(
                run_id, RunStatus.AWAITING_APPROVAL, f"{sku} at {node}: proposal ready for review"
            )

    async def _fail(self, run_id: str, reason: str) -> None:
        async with self._sm() as session:
            written = await repo.update_run(
                session,
                run_id,
                self._clock(),
                expected=RunStatus.RUNNING,
                status=RunStatus.FAILED,
                error=reason,
            )
            await session.commit()
        if written:
            await self._tell(run_id, RunStatus.FAILED, f"Run failed: {reason}")

    async def _tell(self, run_id: str, status: RunStatus, message: str) -> None:
        """Best effort: a broken notifier never changes the run's outcome."""
        if self._notify is None:
            return
        try:
            await self._notify(run_id, status.value, message)
        except Exception:
            logger.exception("could not send notification", extra={"run_id": run_id})

    async def drain(self) -> None:
        """Wait for every background run (tests, graceful shutdown)."""
        while self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def shutdown(self) -> None:
        """Stop background runs; their rows stay `running` for recover() on the next start."""
        for task in self._tasks:
            task.cancel()
        await self.drain()

    async def recover(self) -> int:
        """Re-run rows a restart left `running` (safe: nothing before the gate has effects).

        Rows left `executing` may hold a PO in the ERP, so a human checks them instead.
        """
        async with self._sm() as session:
            for run_id in await repo.list_run_ids_by_status(session, RunStatus.EXECUTING):
                await repo.update_run(
                    session,
                    run_id,
                    self._clock(),
                    expected=RunStatus.EXECUTING,
                    status=RunStatus.NEEDS_HUMAN,
                    error="interrupted during ERP execution; check the ERP before acting",
                )
            await session.commit()
            ids = await repo.list_run_ids_by_status(session, RunStatus.RUNNING)
            rows = [await repo.get_run(session, run_id) for run_id in ids]
        for row in rows:
            if row is not None:
                self._schedule(row.id, row.sku, row.node_code)
        return len(rows)

    # ---- the buyer's decision -------------------------------------------------------------

    async def get_run(self, run_id: str) -> RunOut:
        async with self._sm() as session:
            row = await repo.get_run(session, run_id)
            if row is None:
                raise NotFound(f"Run {run_id} not found", {"run_id": run_id})
            return _out(row)

    async def decide(self, run_id: str, human: HumanDecision, user_id: str | None = None) -> RunOut:
        """Apply the buyer's decision. Only a run awaiting approval accepts one (else 409)."""
        await self.get_run(run_id)  # 404 before 409
        async with self._sm() as session:
            claimed = await repo.claim(
                session, run_id, RunStatus.AWAITING_APPROVAL, RunStatus.EXECUTING, self._clock()
            )
            await session.commit()
        if not claimed:
            raise Conflict(f"Run {run_id} is not waiting for a decision", {"run_id": run_id})
        progress = _Progress()
        try:
            await self._apply(run_id, human, progress, user_id)
        except BaseException as exc:  # cancellation too: never leave the run `executing`
            await asyncio.shield(self._release(run_id, progress, f"{type(exc).__name__}: {exc}"))
            raise
        out = await self.get_run(run_id)
        if out.status in _NOTIFY_AFTER_DECISION:
            await self._tell(run_id, out.status, f"{out.sku} at {out.node}: {out.status.value}")
        return out

    async def _release(self, run_id: str, progress: "_Progress", error: str) -> None:
        """Before the ERP was touched the buyer may simply retry; after, a human must check it."""
        status = RunStatus.NEEDS_HUMAN if progress.erp_touched else RunStatus.AWAITING_APPROVAL
        async with self._sm() as session:
            await repo.update_run(
                session,
                run_id,
                self._clock(),
                expected=RunStatus.EXECUTING,
                status=status,
                error=error,
            )
            await session.commit()

    async def _apply(
        self, run_id: str, human: HumanDecision, progress: "_Progress", user_id: str | None
    ) -> None:
        now = self._clock()
        decision = human.model_dump(mode="json")
        by: dict[str, Any] = {"decided_by": user_id}
        async with self._sm() as session:
            row = await repo.get_run(session, run_id)
            assert row is not None  # claimed above
            p = ProposalOut.model_validate(row.proposal)

            if human.action is HumanAction.REJECT:
                self._learn(session, row, human, now)
                await repo.update_run(
                    session,
                    run_id,
                    now,
                    status=RunStatus.REJECTED,
                    decision=decision,
                    error=None,
                    **by,
                )
                await session.commit()
                return
            if human.action is HumanAction.ACKNOWLEDGE:
                await repo.update_run(
                    session,
                    run_id,
                    now,
                    status=RunStatus.ACKNOWLEDGED,
                    decision=decision,
                    error=None,
                    **by,
                )
                await session.commit()
                return

            inp = _with_erp_terms(
                await planning.load_planning_input(
                    session, row.sku, row.node_code, now.date(), settings=self._s.planning
                ),
                row,
            )
            qty = p.qty
            if human.action is HumanAction.MODIFY:
                error = self._check_modify(human, inp, now)
                if error:
                    await repo.update_run(
                        session, run_id, now, status=RunStatus.AWAITING_APPROVAL, error=error
                    )
                    await session.commit()
                    return
                qty = human.qty
                self._learn(session, row, human, now)
            elif not (p.valid and p.outcome is Outcome.PROPOSE and p.qty):
                # Nothing orderable was proposed (escalation, no-buy): approving acknowledges it.
                await repo.update_run(
                    session,
                    run_id,
                    now,
                    status=RunStatus.ACKNOWLEDGED,
                    decision=decision,
                    error=None,
                    **by,
                )
                await session.commit()
                return
            if not qty:  # a MODIFY to 0 is a valid no-buy
                await repo.update_run(
                    session,
                    run_id,
                    now,
                    status=RunStatus.REJECTED,
                    decision=decision,
                    error=None,
                    **by,
                )
                await session.commit()
                return

            order = ApprovedOrder(
                proposal_id=run_id,
                node_code=row.node_code,
                sku=row.sku,
                supplier_code=inp.supplier_code,
                qty=qty,
                case_pack=inp.case_pack,
                unit_price_inr=inp.unit_cost_inr,
                eta=now.date() + timedelta(days=inp.lead_time_days),
                replans_done=row.replans_done,
            )
            progress.erp_touched = True
            result = await execution.execute(session, order, now.date(), now, self._s)
            values: dict[str, Any] = {
                "decision": decision,
                "execution": result.model_dump(mode="json"),
                "error": None,
                **by,
            }
            if result.status is ExecutionStatus.REPLAN_REQUIRED:
                values |= await self._replanned(session, row, p, inp, result, now)
            else:
                values["status"] = _EXECUTION_TO_RUN[result.status]
            await repo.update_run(session, run_id, now, **values)
            await session.commit()

    @staticmethod
    def _learn(session: AsyncSession, row: AgentRun, human: HumanDecision, now: datetime) -> None:
        """A reasoned REJECT or MODIFY becomes a pending lesson for the buyer to confirm (D25)."""
        if human.reason and human.reason.strip():
            memory.record_feedback(session, row.id, row.sku, row.node_code, human.reason, now)

    def _check_modify(self, human: HumanDecision, inp: PlanningInput, now: datetime) -> str | None:
        if human.qty is None:
            return "modify needs a quantity"
        calc = planning.calculate(inp, self._s.planning)
        flags = validation.check_data_quality(inp, now, self._s.data_quality)
        proposed = ProposedDecision(
            verdict=human_verdict(human.qty, inp.rec_qty),
            qty=human.qty,
            deviation_reason=human.reason,
        )
        v = validation.validate(proposed, inp, calc, tuple(flags), self._s.planning)
        return None if v.valid else "; ".join(validation_feedback(v))

    async def _replanned(
        self,
        session: AsyncSession,
        row: AgentRun,
        p: ProposalOut,
        inp: PlanningInput,
        result: ExecutionResult,
        now: datetime,
    ) -> dict[str, Any]:
        """The ERP changed material terms: re-propose at its terms and wait for the buyer again."""
        assert result.replan is not None and result.erp_number is not None
        po = await erp.get(session, result.erp_number)
        terms = {"unit_cost_inr": po.unit_price_inr, "case_pack": po.case_pack}
        changed = inp.model_copy(update=terms)
        calc = result.replan
        flags = validation.check_data_quality(changed, now, self._s.data_quality)
        v = validation.validate(
            validation.baseline_decision(calc), changed, calc, tuple(flags), self._s.planning
        )
        proposal = p.model_copy(
            update={
                "baseline_qty": calc.qty,
                "verdict": v.verdict,
                "qty": v.qty,
                "outcome": v.outcome,
                "valid": v.valid,
                "reasons": [*result.notes],
                "deviation_reason": None,
                "flags": list(v.flags),
                "issues": list(v.issues) + [x.message for x in v.violations],
                "suggestions": list(v.suggestions),
            }
        )
        return {
            "status": RunStatus.AWAITING_APPROVAL,
            "proposal": proposal.model_dump(mode="json"),
            "replans_done": row.replans_done + 1,
            "unit_price_override": po.unit_price_inr,
            "case_pack_override": po.case_pack,
        }
