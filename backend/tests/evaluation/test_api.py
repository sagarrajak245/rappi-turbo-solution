from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.main import create_app
from app.modules.evaluation.router import get_store
from app.modules.evaluation.runner import run_evaluation


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_store] = lambda: sessionmaker
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_list_and_get_eval_runs(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    out = await run_evaluation(sessionmaker, sessionmaker, get_settings())
    listed = await client.get("/evaluation/runs")
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [out.id]
    assert "results" not in listed.json()[0]

    one = await client.get(f"/evaluation/runs/{out.id}")
    assert one.status_code == 200
    assert one.json()["summary"]["hard_violations"] == 0
    assert len(one.json()["results"]) == len(out.results)


async def test_unknown_eval_run_is_404(client: AsyncClient) -> None:
    assert (await client.get("/evaluation/runs/9999")).status_code == 404
