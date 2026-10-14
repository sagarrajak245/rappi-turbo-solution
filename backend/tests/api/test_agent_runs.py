"""HTTP surface of the agent: start a run to the human gate, then resume it with a decision.

The real graph runs over a seeded database; the LLMs are scripted, so no network is used.
"""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.main import create_app
from app.modules.agent.llm.fake import ScriptedLlm
from app.modules.agent.router import get_agent_service
from app.modules.agent.service import AgentService
from app.seed.scenario1 import seed_scenario1

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)

ACCEPT_800: dict[str, Any] = {
    "verdict": "ACCEPT",
    "qty": 800,
    "reasons": ["need 800 matches the recommendation"],
}


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async with sessionmaker() as s:
        await seed_scenario1(s, today=TODAY, now=NOW)
    svc = AgentService(
        sessionmaker,
        ScriptedLlm([ACCEPT_800]),
        ScriptedLlm([{"ok": True, "issues": []}]),
        get_settings(),
        clock=lambda: NOW,
    )
    app = create_app()
    app.dependency_overrides[get_agent_service] = lambda: svc
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_start_then_approve(client: AsyncClient) -> None:
    started = await client.post("/agent/runs", json={"sku": "COKE-750", "node": "BANDRA"})
    assert started.status_code == 200
    proposal = started.json()
    assert proposal["verdict"] == "ACCEPT"
    assert proposal["qty"] == 800

    resumed = await client.post(
        f"/agent/runs/{proposal['thread_id']}/resume", json={"action": "approve"}
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "approved"
    assert resumed.json()["qty"] == 800


async def test_resume_twice_is_conflict(client: AsyncClient) -> None:
    started = await client.post("/agent/runs", json={"sku": "COKE-750", "node": "BANDRA"})
    url = f"/agent/runs/{started.json()['thread_id']}/resume"
    await client.post(url, json={"action": "approve"})
    again = await client.post(url, json={"action": "approve"})
    assert again.status_code == 409


async def test_resume_unknown_run_is_not_found(client: AsyncClient) -> None:
    r = await client.post("/agent/runs/nope/resume", json={"action": "approve"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_empty_sku_is_rejected(client: AsyncClient) -> None:
    r = await client.post("/agent/runs", json={"sku": "", "node": "BANDRA"})
    assert r.status_code == 422


async def test_without_llm_provider_is_unavailable() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/agent/runs", json={"sku": "COKE-750", "node": "BANDRA"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "llm_unavailable"
