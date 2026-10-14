"""Learning loop (D25, L1-L3): buyer feedback becomes a pending lesson, the buyer confirms it,
and the next run for the same SKU x node sees it. Lessons never loosen hard constraints."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.modules.agent.llm.fake import ScriptedLlm
from app.modules.agent.schemas import HumanAction, HumanDecision
from app.modules.agent.service import AgentService
from app.modules.memory import service as memory
from app.modules.memory.models import Lesson
from app.seed.scenario1 import seed_scenario1
from app.shared.enums import LessonStatus, Outcome, RunStatus

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
OK = {"ok": True, "issues": []}
TEXT = "Bandra weekends are slower; order less before them"


def accept(qty: int) -> dict[str, Any]:
    return {"verdict": "ACCEPT", "qty": qty, "reasons": [f"need {qty} matches the recommendation"]}


@pytest.fixture
async def seeded(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as s:
        await seed_scenario1(s, today=TODAY, now=NOW)


def make(
    sm: async_sessionmaker[AsyncSession], decide: list[dict[str, Any] | Exception]
) -> tuple[AgentService, ScriptedLlm]:
    llm = ScriptedLlm(decide)
    svc = AgentService(sm, llm, ScriptedLlm([OK] * len(decide)), get_settings(), clock=lambda: NOW)
    return svc, llm


async def add_lesson(sm: async_sessionmaker[AsyncSession], status: LessonStatus) -> int:
    async with sm() as s:
        row = Lesson(
            sku="COKE-750",
            node_code="BANDRA",
            text=TEXT,
            status=status,
            times_applied=0,
            created_at=NOW,
            updated_at=NOW,
        )
        s.add(row)
        await s.commit()
        return row.id


@pytest.mark.usefixtures("seeded")
async def test_l1_feedback_becomes_a_lesson_applied_and_cited_next_run(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    svc, llm = make(sessionmaker, [accept(800), accept(800)])
    first = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()
    await svc.decide(first.id, HumanDecision(action=HumanAction.REJECT, reason=TEXT))

    async with sessionmaker() as s:
        pending = await memory.list_lessons(s, LessonStatus.PENDING)
    # the lesson keeps what the buyer did, not only why, so the next prompt has the context
    assert [(x.text, x.sku, x.node, x.source_run_id) for x in pending] == [
        (f"Buyer rejected the proposed 800. Reason: {TEXT}", "COKE-750", "BANDRA", first.id)
    ]
    async with sessionmaker() as s:
        await memory.confirm(s, pending[0].id, NOW)

    second = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()
    run = await svc.get_run(second.id)
    assert run.status is RunStatus.AWAITING_APPROVAL
    assert TEXT in llm.calls[1][1]
    assert run.proposal is not None and run.proposal.lessons_applied == [pending[0].id]
    async with sessionmaker() as s:
        (active,) = await memory.list_lessons(s, LessonStatus.ACTIVE)
    assert active.times_applied == 1


@pytest.mark.usefixtures("seeded")
async def test_l2_a_lesson_never_lets_a_hard_constraint_through(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await add_lesson(sessionmaker, LessonStatus.ACTIVE)
    huge = {"verdict": "MODIFY", "qty": 960000, "deviation_reason": TEXT}
    svc, llm = make(sessionmaker, [huge, huge])
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()

    p = (await svc.get_run(run.id)).proposal
    assert TEXT in llm.calls[0][1]
    assert p is not None and p.outcome is Outcome.ESCALATE and p.qty != 960000


@pytest.mark.usefixtures("seeded")
async def test_l3_disabled_lesson_is_not_applied(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    await add_lesson(sessionmaker, LessonStatus.DISABLED)
    svc, llm = make(sessionmaker, [accept(800)])
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()

    assert TEXT not in llm.calls[0][1]
    p = (await svc.get_run(run.id)).proposal
    assert p is not None and p.lessons_applied == []


@pytest.mark.usefixtures("seeded")
async def test_approve_without_feedback_records_no_lesson(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    svc, _ = make(sessionmaker, [accept(800)])
    run = await svc.start_run("COKE-750", "BANDRA")
    await svc.drain()
    await svc.decide(run.id, HumanDecision(action=HumanAction.REJECT))
    async with sessionmaker() as s:
        assert await memory.list_lessons(s, None) == []
