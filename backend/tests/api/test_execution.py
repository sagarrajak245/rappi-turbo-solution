"""HTTP surface of the execution loop: one approved order in, the observed outcome out."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_session
from app.main import create_app
from app.seed.scenario1 import seed_scenario1

TODAY = datetime.now(UTC).date()


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async with sessionmaker() as s:
        await seed_scenario1(s, today=TODAY, now=datetime.now(UTC))
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def body(eta: date) -> dict[str, object]:
    return {
        "proposal_id": "prop-api-1",
        "node_code": "ANDHERI-W",
        "sku": "NESCAFE-50",
        "supplier_code": "NESTLE",
        "qty": 230,
        "case_pack": 10,
        "unit_price_inr": "180.00",
        "eta": eta.isoformat(),
    }


async def test_execute_returns_replan_for_price_surprise(client: AsyncClient) -> None:
    res = await client.post("/execution/orders", json=body(TODAY + timedelta(days=3)))
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "replan_required"
    assert data["replan"]["qty"] == 210


async def test_invalid_order_uses_error_envelope(client: AsyncClient) -> None:
    res = await client.post("/execution/orders", json={**body(TODAY), "qty": 0})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_failed"
