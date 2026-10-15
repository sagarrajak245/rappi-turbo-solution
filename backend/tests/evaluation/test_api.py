from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.main import create_app
from app.modules.auth.deps import current_user
from app.modules.auth.schemas import UserOut
from app.modules.evaluation.jobs import EvalJobs
from app.modules.evaluation.router import get_jobs, get_store
from app.modules.evaluation.runner import run_evaluation
from app.shared.enums import UserRole


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_store] = lambda: sessionmaker
    app.dependency_overrides[current_user] = lambda: UserOut(
        id="a", name="n", email="e", role=UserRole.ADMIN, branch="Mumbai"
    )
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


async def test_admin_starts_an_eval_run(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app()
    jobs = EvalJobs(sessionmaker, get_settings())
    app.dependency_overrides[get_jobs] = lambda: jobs
    app.dependency_overrides[current_user] = lambda: UserOut(
        id="a", name="n", email="e", role=UserRole.ADMIN, branch="Mumbai"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        started = await c.post("/evaluation/runs", json={"live": False})
        assert started.status_code == 202
        assert started.json()["finished_at"] is None
        assert (await c.post("/evaluation/runs", json={"live": False})).status_code == 409
    await jobs.drain()


async def test_buyer_cannot_start_an_eval_run(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app()
    app.dependency_overrides[get_jobs] = lambda: EvalJobs(sessionmaker, get_settings())
    app.dependency_overrides[current_user] = lambda: UserOut(
        id="b", name="n", email="e", role=UserRole.BUYER, branch="Mumbai"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.post("/evaluation/runs", json={"live": False})).status_code == 403
