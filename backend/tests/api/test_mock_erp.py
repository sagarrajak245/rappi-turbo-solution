"""HTTP surface of the mock ERP.

The client runs the app on the test's own event loop (ASGITransport), so the shared async DB
fixtures work on Postgres too, not only SQLite.
"""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_session
from app.main import create_app
from app.modules.erp_mock.models import ErpBehaviour, ErpPurchaseOrder

BASE = "/mock-erp/purchase-orders"
BODY: dict[str, Any] = {
    "node_code": "N1",
    "sku": "SKU1",
    "supplier_code": "SUP1",
    "qty": 240,
    "case_pack": 24,
    "unit_price_inr": "10.00",
    "eta": "2026-10-20",
}


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def h(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


async def _po_count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as s:
        return (await s.execute(select(func.count()).select_from(ErpPurchaseOrder))).scalar_one()


async def test_create_twice_same_key_is_one_po(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    a = await client.post(BASE, json=BODY, headers=h("k1"))
    b = await client.post(BASE, json=BODY, headers=h("k1"))
    assert a.status_code == 201
    assert b.json()["erp_number"] == a.json()["erp_number"]
    assert await _po_count(sessionmaker) == 1


async def test_missing_idempotency_key_is_422_envelope(client: AsyncClient) -> None:
    r = await client.post(BASE, json=BODY)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


async def test_get_submit_cancel_flow(client: AsyncClient) -> None:
    number = (await client.post(BASE, json=BODY, headers=h("k1"))).json()["erp_number"]
    assert (await client.get(f"{BASE}/{number}")).json()["status"] == "draft"
    sub = await client.post(f"{BASE}/{number}/submit", headers=h("s1"))
    assert sub.status_code == 200
    assert sub.json()["status"] == "submitted"
    assert (await client.post(f"{BASE}/{number}/submit", headers=h("s2"))).status_code == 409
    cancel = await client.post(f"{BASE}/{number}/cancel", headers=h("c1"))
    assert cancel.json()["status"] == "cancelled"


async def test_unknown_po_is_404_envelope(client: AsyncClient) -> None:
    r = await client.get(f"{BASE}/ERP-NOPE")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_timeout_is_504_and_retry_returns_po(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker() as s:
        s.add(ErpBehaviour(node_code="N1", sku="SKU1", behaviour="timeout_after_create", params={}))
        await s.commit()
    first = await client.post(BASE, json=BODY, headers=h("k1"))
    assert first.status_code == 504
    assert first.json()["error"]["code"] == "erp_timeout"
    retry = await client.post(BASE, json=BODY, headers=h("k1"))
    assert retry.status_code == 201
    assert await _po_count(sessionmaker) == 1
