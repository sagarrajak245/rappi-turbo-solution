"""HTTP surface of the agent: start a run (202), poll it, then send the buyer's decision.

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
async def svc(sessionmaker: async_sessionmaker[AsyncSession]) -> AgentService:
    async with sessionmaker() as s:
        await seed_scenario1(s, today=TODAY, now=NOW)
    return AgentService(
        sessionmaker,
        ScriptedLlm([ACCEPT_800]),
        ScriptedLlm([{"ok": True, "issues": []}]),
        get_settings(),
        clock=lambda: NOW,
    )


@pytest.fixture
async def client(svc: AgentService) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_agent_service] = lambda: svc
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _proposed(client: AsyncClient, svc: AgentService) -> str:
    started = await client.post("/agent/runs", json={"sku": "COKE-750", "node": "BANDRA"})
    assert started.status_code == 202
    assert started.json()["status"] == "running"
    await svc.drain()
    return str(started.json()["id"])


async def test_start_poll_then_approve(client: AsyncClient, svc: AgentService) -> None:
    run_id = await _proposed(client, svc)
    run = (await client.get(f"/agent/runs/{run_id}")).json()
    assert run["status"] == "awaiting_approval"
    assert (run["proposal"]["verdict"], run["proposal"]["qty"]) == ("ACCEPT", 800)

    done = await client.post(f"/agent/runs/{run_id}/decision", json={"action": "approve"})
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    assert done.json()["execution"]["final_status"] == "submitted"


async def test_second_decision_is_conflict(client: AsyncClient, svc: AgentService) -> None:
    url = f"/agent/runs/{await _proposed(client, svc)}/decision"
    await client.post(url, json={"action": "reject", "reason": "not now"})
    again = await client.post(url, json={"action": "approve"})
    assert again.status_code == 409


async def test_unknown_run_is_not_found(client: AsyncClient) -> None:
    r = await client.post("/agent/runs/nope/decision", json={"action": "approve"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert (await client.get("/agent/runs/nope")).status_code == 404


async def test_empty_sku_is_rejected(client: AsyncClient) -> None:
    r = await client.post("/agent/runs", json={"sku": "", "node": "BANDRA"})
    assert r.status_code == 422


async def test_without_llm_provider_is_unavailable() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/agent/runs", json={"sku": "COKE-750", "node": "BANDRA"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "llm_unavailable"
