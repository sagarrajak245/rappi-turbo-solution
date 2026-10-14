"""Offline evaluation: an oracle LLM answers each case's expected decision."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.modules.evaluation import service
from app.modules.evaluation.runner import run_evaluation
from app.scenarios.scenario1 import CASES


async def test_offline_eval_passes_every_case(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    out = await run_evaluation(sessionmaker, sessionmaker, get_settings())
    failed = [r.case_id for r in out.results if not r.passed]
    assert failed == []
    assert len(out.results) == len(CASES)
    assert out.mode == "offline"
    assert out.summary["accuracy"] == 1.0
    assert out.summary["hard_violations"] == 0
    assert 0.0 <= out.summary["escalation_rate"] <= 1.0


async def test_repeat_multiplies_results_and_is_persisted(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    out = await run_evaluation(sessionmaker, sessionmaker, get_settings(), repeat=2)
    assert len(out.results) == 2 * len(CASES)
    async with sessionmaker() as s:
        stored = await service.get_run(s, out.id)
        listed = await service.list_runs(s)
    assert len(stored.results) == 2 * len(CASES)
    assert [r.id for r in listed] == [out.id]
