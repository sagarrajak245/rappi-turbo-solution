from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.observability import repository as repo
from app.modules.observability.schemas import LlmUsage, Metrics


async def metrics(session: AsyncSession) -> Metrics:
    by_status = {status.value: n for status, n in await repo.run_counts(session)}
    usage = [
        LlmUsage(
            provider=p,
            model=m,
            calls=calls,
            tokens_in=ti,
            tokens_out=to,
            cost_usd=cost,
            fallback_calls=fb,
        )
        for p, m, calls, ti, to, cost, fb in await repo.llm_usage(session)
    ]
    total_runs = sum(by_status.values())
    total_calls = sum(u.calls for u in usage)
    total_cost = sum(u.cost_usd for u in usage)
    fallbacks = sum(u.fallback_calls for u in usage)
    return Metrics(
        runs_by_status=by_status,
        total_runs=total_runs,
        llm=usage,
        total_llm_calls=total_calls,
        total_cost_usd=total_cost,
        avg_cost_per_run=total_cost / total_runs if total_runs else 0.0,
        fallback_rate=fallbacks / total_calls if total_calls else 0.0,
    )
