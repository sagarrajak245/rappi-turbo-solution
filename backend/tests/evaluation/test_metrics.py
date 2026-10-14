from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.main import create_app
from app.models import AgentRun, LlmCall
from app.modules.observability import service
from app.modules.observability.router import get_store
from app.shared.enums import RunStatus

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


def _run(rid: str, status: RunStatus) -> AgentRun:
    return AgentRun(
        id=rid, sku="S", node_code="N", status=status, replans_done=0, created_at=NOW, updated_at=NOW
    )


def _call(rid: str, model: str, cost: str, fallback: bool = False) -> LlmCall:
    return LlmCall(
        run_id=rid,
        provider="p",
        model=model,
        tokens_in=100,
        tokens_out=10,
        latency_ms=5,
        cost_usd=Decimal(cost),
        fallback_used=fallback,
        created_at=NOW,
    )


@pytest.fixture
async def seeded(sessionmaker: async_sessionmaker[AsyncSession]) -> async_sessionmaker[AsyncSession]:
    async with sessionmaker() as s:
        s.add_all(
            [
                _run("a", RunStatus.COMPLETED),
                _run("b", RunStatus.COMPLETED),
                _run("c", RunStatus.FAILED),
            ]
        )
        await s.flush()
        s.add_all(
            [
                _call("a", "m1", "0.010000"),
                _call("a", "m1", "0.020000", fallback=True),
                _call("b", "m2", "0.030000"),
                _call("c", "m2", "0.040000"),
            ]
        )
        await s.commit()
    return sessionmaker


async def test_metrics_aggregate(seeded: async_sessionmaker[AsyncSession]) -> None:
    async with seeded() as s:
        m = await service.metrics(s)
    assert m.runs_by_status == {"completed": 2, "failed": 1}
    assert m.total_runs == 3
    by_model = {(x.provider, x.model): x for x in m.llm}
    assert by_model[("p", "m1")].calls == 2
    assert by_model[("p", "m1")].tokens_in == 200
    assert by_model[("p", "m2")].cost_usd == pytest.approx(0.07)
    assert m.total_cost_usd == pytest.approx(0.10)
    assert m.avg_cost_per_run == pytest.approx(0.10 / 3)
    assert m.fallback_rate == pytest.approx(0.25)


async def test_metrics_empty(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as s:
        m = await service.metrics(s)
    assert (m.total_runs, m.avg_cost_per_run, m.fallback_rate, m.llm) == (0, 0.0, 0.0, [])


async def test_metrics_endpoint(seeded: async_sessionmaker[AsyncSession]) -> None:
    app = create_app()
    app.dependency_overrides[get_store] = lambda: seeded
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/admin/metrics")
    assert resp.status_code == 200
    assert resp.json()["total_runs"] == 3
