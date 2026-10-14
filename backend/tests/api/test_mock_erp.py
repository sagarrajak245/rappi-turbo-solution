"""HTTP surface of the mock ERP."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_session
from app.main import create_app
from app.modules.erp_mock.models import ErpBehaviour, ErpPurchaseOrder
from tests.integration import conftest as _db

# Reuse the integration DB fixtures (SQLite temp file, or TEST_DATABASE_URL).
engine = _db.engine
sessionmaker = _db.sessionmaker

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
def client(sessionmaker: async_sessionmaker[AsyncSession]) -> Iterator[TestClient]:
    app = create_app()

    async def _session() -> Any:
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as c:
        yield c


def h(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


async def test_create_twice_same_key_is_one_po(
    client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    a = client.post(BASE, json=BODY, headers=h("k1"))
    b = client.post(BASE, json=BODY, headers=h("k1"))
    assert a.status_code == 201
    assert b.json()["erp_number"] == a.json()["erp_number"]
    async with sessionmaker() as s:
        count = (await s.execute(select(func.count()).select_from(ErpPurchaseOrder))).scalar_one()
    assert count == 1


def test_missing_idempotency_key_is_422(client: TestClient) -> None:
    assert client.post(BASE, json=BODY).status_code == 422


def test_get_submit_cancel_flow(client: TestClient) -> None:
    number = client.post(BASE, json=BODY, headers=h("k1")).json()["erp_number"]
    assert client.get(f"{BASE}/{number}").json()["status"] == "draft"
    sub = client.post(f"{BASE}/{number}/submit", headers=h("s1"))
    assert sub.status_code == 200
    assert sub.json()["status"] == "submitted"
    assert client.post(f"{BASE}/{number}/submit", headers=h("s2")).status_code == 409
    assert client.post(f"{BASE}/{number}/cancel", headers=h("c1")).json()["status"] == "cancelled"


def test_unknown_po_is_404_envelope(client: TestClient) -> None:
    r = client.get(f"{BASE}/ERP-NOPE")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_timeout_is_504_and_retry_returns_po(
    client: TestClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker() as s:
        s.add(ErpBehaviour(node_code="N1", sku="SKU1", behaviour="timeout_after_create", params={}))
        await s.commit()
    first = client.post(BASE, json=BODY, headers=h("k1"))
    assert first.status_code == 504
    assert first.json()["error"]["code"] == "erp_timeout"
    retry = client.post(BASE, json=BODY, headers=h("k1"))
    assert retry.status_code == 201
    async with sessionmaker() as s:
        count = (await s.execute(select(func.count()).select_from(ErpPurchaseOrder))).scalar_one()
    assert count == 1
