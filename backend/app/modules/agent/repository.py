"""Queries for agent runs and their LLM calls. No business rules here."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.llm.base import LlmCallRecord
from app.modules.agent.models import AgentRun, LlmCall
from app.shared.enums import RunStatus


async def get_run(session: AsyncSession, run_id: str) -> AgentRun | None:
    return await session.get(AgentRun, run_id)


async def list_run_ids_by_status(session: AsyncSession, status: RunStatus) -> Sequence[str]:
    stmt = select(AgentRun.id).where(AgentRun.status == status).order_by(AgentRun.created_at)
    return (await session.execute(stmt)).scalars().all()


async def claim(
    session: AsyncSession, run_id: str, expected: RunStatus, new: RunStatus, now: datetime
) -> bool:
    """Compare-and-set the status; False when another request moved the run first."""
    stmt = (
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status == expected)
        .values(status=new, updated_at=now)
    )
    result = await session.execute(stmt)
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def update_run(
    session: AsyncSession,
    run_id: str,
    now: datetime,
    expected: RunStatus | None = None,
    **values: Any,
) -> bool:
    """Write the run; with `expected`, only while it still has that status (compare-and-set)."""
    stmt = update(AgentRun).where(AgentRun.id == run_id)
    if expected is not None:
        stmt = stmt.where(AgentRun.status == expected)
    result = await session.execute(stmt.values(updated_at=now, **values))
    return bool(result.rowcount)  # type: ignore[attr-defined]


def add_llm_calls(
    session: AsyncSession, run_id: str, records: Sequence[LlmCallRecord], now: datetime
) -> None:
    session.add_all(
        LlmCall(
            run_id=run_id,
            provider=r.provider,
            model=r.model,
            tokens_in=r.tokens_in,
            tokens_out=r.tokens_out,
            latency_ms=r.latency_ms,
            cost_usd=Decimal(str(r.cost_usd)),
            fallback_used=r.fallback_used,
            created_at=now,
        )
        for r in records
    )
