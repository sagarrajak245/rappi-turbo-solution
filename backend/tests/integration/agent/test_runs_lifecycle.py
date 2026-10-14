"""A run is a persisted record: decide in the background, wait for the buyer, execute in the ERP.

Scripted LLMs over the seeded database; the mock ERP plays the supplier (F1 price rise).
"""

import asyncio
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import Conflict, NotFound
from app.modules.agent.llm.base import LlmCallRecord, T
from app.modules.agent.llm.fake import ScriptedLlm
from app.modules.agent.models import AgentRun, LlmCall
from app.modules.agent.schemas import HumanAction, HumanDecision
from app.modules.agent.service import AgentService
from app.seed.scenario1 import seed_scenario1
from app.shared.enums import ErpPoStatus, RunStatus

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
OK = {"ok": True, "issues": []}
APPROVE = HumanDecision(action=HumanAction.APPROVE)


def accept(qty: int) -> dict[str, Any]:
    return {"verdict": "ACCEPT", "qty": qty, "reasons": [f"need {qty} matches the recommendation"]}


@pytest.fixture
async def seeded(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as s:
        await seed_scenario1(s, today=TODAY, now=NOW)


def make(
    sm: async_sessionmaker[AsyncSession],
    decide: list[dict[str, Any] | Exception],
    settings: Settings | None = None,
    decide_llm: Any = None,
) -> AgentService:
    return AgentService(
        sm,
        decide_llm or ScriptedLlm(decide),
        ScriptedLlm([OK] * len(decide)),
        settings or get_settings(),
        clock=lambda: NOW,
    )


async def llm_rows(sm: async_sessionmaker[AsyncSession], run_id: str) -> int:
    async with sm() as s:
        stmt = select(func.count()).select_from(LlmCall).where(LlmCall.run_id == run_id)
        return (await s.execute(stmt)).scalar_one()


@pytest.mark.usefixtures("seeded")
async def test_run_decides_in_background_then_waits_for_the_buyer(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    svc = make(sessionmaker, [accept(800)])
    started = await svc.start_run("COKE-750", "BANDRA")
    assert started.status is RunStatus.RUNNING
    await svc.drain()

    run = await svc.get_run(started.id)
    assert run.status is RunStatus.AWAITING_APPROVAL
    assert run.proposal is not None and run.proposal.qty == 800
    assert await llm_rows(sessionmaker, run.id) == 2  # decide + review


@pytest.mark.usefixtures("seeded")
async def test_approve_executes_in_the_erp(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    svc = make(sessionmaker, [accept(800)])
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()

    done = await svc.decide(run.id, APPROVE)
    assert done.status is RunStatus.COMPLETED
    assert done.execution is not None
    assert done.execution.final_status is ErpPoStatus.SUBMITTED


@pytest.mark.usefixtures("seeded")
async def test_reject_and_second_decision_conflicts(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    svc = make(sessionmaker, [accept(800)])
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()

    rejected = await svc.decide(run.id, HumanDecision(action=HumanAction.REJECT, reason="no"))
    assert rejected.status is RunStatus.REJECTED
    with pytest.raises(Conflict):
        await svc.decide(run.id, APPROVE)
    with pytest.raises(NotFound):
        await svc.get_run("missing")


@pytest.mark.usefixtures("seeded")
async def test_f1_price_rise_replans_then_completes(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    svc = make(sessionmaker, [accept(230)])
    run = await svc.start_run("NESCAFE-50", "ANDHERI-W")
    await svc.drain()

    replanned = await svc.decide(run.id, APPROVE)
    assert replanned.status is RunStatus.AWAITING_APPROVAL
    assert replanned.replans_done == 1
    assert replanned.proposal is not None and replanned.proposal.qty == 210

    done = await svc.decide(run.id, APPROVE)
    assert done.status is RunStatus.COMPLETED
    assert done.execution is not None and done.execution.final_status is ErpPoStatus.SUBMITTED


@pytest.mark.usefixtures("seeded")
async def test_modify_with_invalid_qty_keeps_waiting(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    svc = make(sessionmaker, [accept(800)])
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()

    bad = await svc.decide(run.id, HumanDecision(action=HumanAction.MODIFY, qty=7, reason="x"))
    assert bad.status is RunStatus.AWAITING_APPROVAL
    assert bad.error


class _SlowLlm:
    async def complete_json(
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, LlmCallRecord]:
        await asyncio.sleep(5)
        raise AssertionError("deadline should have fired")


@pytest.mark.usefixtures("seeded")
async def test_run_past_its_deadline_fails(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    s = get_settings()
    fast = s.model_copy(update={"llm": s.llm.model_copy(update={"run_deadline_s": 0.05})})
    svc = make(sessionmaker, [], settings=fast, decide_llm=_SlowLlm())
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()

    failed = await svc.get_run(run.id)
    assert failed.status is RunStatus.FAILED
    assert failed.error


@pytest.mark.usefixtures("seeded")
async def test_recover_reruns_runs_interrupted_by_a_restart(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as s:
        s.add(
            AgentRun(
                id="interrupted",
                sku="COKE-750",
                node_code="BANDRA",
                status=RunStatus.RUNNING,
                replans_done=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await s.commit()
    svc = make(sessionmaker, [accept(800)])
    assert await svc.recover() == 1
    await svc.drain()

    run = await svc.get_run("interrupted")
    assert run.status is RunStatus.AWAITING_APPROVAL


@pytest.mark.usefixtures("seeded")
async def test_failure_after_the_erp_was_touched_needs_a_human(
    sessionmaker: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = make(sessionmaker, [accept(230)])
    run = await svc.start_run("NESCAFE-50", "ANDHERI-W")
    await svc.drain()

    async def boom(*_: Any) -> None:
        raise RuntimeError("erp read failed")

    monkeypatch.setattr("app.modules.agent.service.erp.get", boom)
    with pytest.raises(RuntimeError):
        await svc.decide(run.id, APPROVE)  # the draft is already cancelled for re-plan

    stuck = await svc.get_run(run.id)
    assert stuck.status is RunStatus.NEEDS_HUMAN  # never back to the gate: the ERP has a PO
    assert stuck.error
    with pytest.raises(Conflict):
        await svc.decide(run.id, HumanDecision(action=HumanAction.REJECT, reason="no"))


@pytest.mark.usefixtures("seeded")
async def test_recover_hands_runs_interrupted_mid_execution_to_a_human(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as s:
        s.add(
            AgentRun(
                id="mid-erp",
                sku="COKE-750",
                node_code="BANDRA",
                status=RunStatus.EXECUTING,
                replans_done=0,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await s.commit()
    svc = make(sessionmaker, [])
    assert await svc.recover() == 0
    run = await svc.get_run("mid-erp")
    assert run.status is RunStatus.NEEDS_HUMAN and run.error


class _GatedLlm(ScriptedLlm):
    def __init__(self, script: list[dict[str, Any] | Exception], gate: asyncio.Event) -> None:
        super().__init__(script)
        self.gate = gate

    async def complete_json(
        self, system: str, user: str, schema: type[T]
    ) -> tuple[T, LlmCallRecord]:
        await self.gate.wait()
        return await super().complete_json(system, user, schema)


@pytest.mark.usefixtures("seeded")
async def test_a_stale_background_run_never_reopens_a_decided_run(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    gate = asyncio.Event()
    svc = make(sessionmaker, [accept(800)], decide_llm=_GatedLlm([accept(800)], gate))
    run = await svc.start_run("COKE-750", "BANDRA")
    async with sessionmaker() as s:  # another process finished this run meanwhile
        row = await s.get(AgentRun, run.id)
        assert row is not None
        row.status = RunStatus.COMPLETED
        await s.commit()
    gate.set()
    await svc.drain()

    assert (await svc.get_run(run.id)).status is RunStatus.COMPLETED
    assert await llm_rows(sessionmaker, run.id) == 0
