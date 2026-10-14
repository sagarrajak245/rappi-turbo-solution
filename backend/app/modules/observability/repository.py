"""Aggregate queries over agent runs and LLM calls. Aggregation happens in SQL, not in Python."""

from sqlalchemy import Integer, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agent.models import AgentRun, LlmCall
from app.shared.enums import RunStatus


async def run_counts(session: AsyncSession) -> list[tuple[RunStatus, int]]:
    rows = await session.execute(select(AgentRun.status, func.count()).group_by(AgentRun.status))
    return [(status, int(n)) for status, n in rows.all()]


async def llm_usage(session: AsyncSession) -> list[tuple[str, str, int, int, int, float, int]]:
    """(provider, model, calls, tokens_in, tokens_out, cost_usd, fallback_calls) per model."""
    stmt = (
        select(
            LlmCall.provider,
            LlmCall.model,
            func.count(),
            func.coalesce(func.sum(LlmCall.tokens_in), 0),
            func.coalesce(func.sum(LlmCall.tokens_out), 0),
            func.coalesce(func.sum(LlmCall.cost_usd), 0),
            func.coalesce(func.sum(case((LlmCall.fallback_used.is_(True), 1), else_=0)), 0).cast(
                Integer
            ),
        )
        .group_by(LlmCall.provider, LlmCall.model)
        .order_by(LlmCall.provider, LlmCall.model)
    )
    rows = await session.execute(stmt)
    return [
        (p, m, int(c), int(ti), int(to), float(cost), int(fb))
        for p, m, c, ti, to, cost, fb in rows.all()
    ]
