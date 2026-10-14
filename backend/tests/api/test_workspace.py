"""Read APIs behind the UI: runs list, inbox, purchase orders and the home dashboard."""

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import get_session
from app.main import create_app
from app.modules.agent.models import AgentRun
from app.modules.auth.deps import current_user
from app.modules.auth.schemas import UserOut
from app.modules.erp_mock.models import ErpPurchaseOrder
from app.modules.workspace.router import get_clock
from app.seed.scenario1 import seed_scenario1
from app.shared.enums import ErpPoStatus, RunStatus, UserRole

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


def _proposal(sku: str, node: str, qty: int, reason: str) -> dict[str, Any]:
    return {
        "thread_id": "t",
        "sku": sku,
        "node": node,
        "rec_qty": 800,
        "baseline_qty": qty,
        "verdict": "MODIFY",
        "qty": qty,
        "outcome": "PROPOSE",
        "valid": True,
        "reasons": [reason, "second"],
    }


def _run(rid: str, sku: str, node: str, status: RunStatus, minutes: int, **kw: Any) -> AgentRun:
    at = NOW + timedelta(minutes=minutes)
    return AgentRun(
        id=rid,
        sku=sku,
        node_code=node,
        status=status,
        proposal=_proposal(sku, node, 600, f"{rid} reason"),
        created_at=at,
        updated_at=at,
        **kw,
    )


@pytest.fixture
async def client(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    async with sessionmaker() as s:
        await seed_scenario1(s, today=TODAY, now=NOW)
        s.add_all(
            [
                _run("stuck", "X-1", "THANE", RunStatus.NEEDS_HUMAN, 0),
                _run(
                    "old",
                    "COKE-750",
                    "BANDRA",
                    RunStatus.REJECTED,
                    1,
                    decision={"action": "reject"},
                ),
                _run("new", "COKE-750", "BANDRA", RunStatus.AWAITING_APPROVAL, 2),
                _run(
                    "done",
                    "COKE-750",
                    "POWAI",
                    RunStatus.COMPLETED,
                    3,
                    decision={"action": "approve"},
                    execution={
                        "status": "completed",
                        "erp_number": "ERP-1",
                        "final_status": "submitted",
                    },
                ),
                ErpPurchaseOrder(
                    erp_number="ERP-1",
                    idempotency_key="k1",
                    node_code="POWAI",
                    sku="COKE-750",
                    supplier_code="SUP",
                    qty=600,
                    case_pack=24,
                    unit_price_inr=Decimal("30"),
                    total_inr=Decimal("18000"),
                    eta=TODAY + timedelta(days=3),
                    status=ErpPoStatus.SUBMITTED,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
        await s.commit()

    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_clock] = lambda: lambda: NOW + timedelta(hours=1)
    app.dependency_overrides[current_user] = lambda: UserOut(
        id="u", name="Sagar", email="e", role=UserRole.BUYER, branch="Mumbai"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_runs_newest_first_and_filtered(client: AsyncClient) -> None:
    rows = (await client.get("/agent/runs")).json()
    assert [r["id"] for r in rows] == ["done", "new", "old", "stuck"]
    assert {"verdict": "MODIFY", "qty": 600, "reason": "new reason"}.items() <= rows[1].items()
    waiting = (await client.get("/agent/runs", params={"status": "awaiting_approval"})).json()
    assert [r["id"] for r in waiting] == ["new"]
    assert len((await client.get("/agent/runs", params={"limit": 1})).json()) == 1


async def test_inbox_joins_names_and_the_latest_run(client: AsyncClient) -> None:
    rows = (await client.get("/recommendations")).json()
    assert len(rows) == 25
    coke = next(r for r in rows if (r["sku"], r["node"]) == ("COKE-750", "BANDRA"))
    assert coke["product_name"] and coke["node_name"] and coke["rec_qty"] > 0
    assert coke["run"]["id"] == "new"
    untouched = [r for r in rows if r["run"] is None]
    assert len(untouched) == 24  # COKE-750 has no recommendation at POWAI
    bandra = (await client.get("/recommendations", params={"node": "BANDRA"})).json()
    assert {r["node"] for r in bandra} == {"BANDRA"}
    waiting = (await client.get("/recommendations", params={"status": "awaiting_approval"})).json()
    assert [r["run"]["id"] for r in waiting] == ["new"]


async def test_purchase_orders_come_from_executed_runs(client: AsyncClient) -> None:
    (po,) = (await client.get("/purchase-orders")).json()
    assert {
        "erp_number": "ERP-1",
        "run_id": "done",
        "sku": "COKE-750",
        "node": "POWAI",
        "qty": 600,
        "status": "submitted",
        "execution_status": "completed",
    }.items() <= po.items()
    assert Decimal(po["total_inr"]) == Decimal("18000")


async def test_dashboard_summary_for_the_buyer(client: AsyncClient) -> None:
    d = (await client.get("/dashboard/summary")).json()
    assert d["pending_approvals"] == 1  # only awaiting_approval accepts a decision
    assert d["needs_attention"] == 1  # needs_human: checked outside the approve flow
    assert Decimal(d["committed_today_inr"]) == Decimal("18000")
    assert d["agreement_pct"] == 50.0  # one approve, one reject
    assert [r["id"] for r in d["needs_decision"]] == ["new"]
    assert {b["node"] for b in d["budgets"]} == {
        "ANDHERI-W",
        "BANDRA",
        "POWAI",
        "LOWER-PAREL",
        "THANE",
    }
    assert all(Decimal(s["capacity"]) > 0 for s in d["storage"])


async def test_reads_need_a_login() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for path in ["/agent/runs", "/recommendations", "/purchase-orders", "/dashboard/summary"]:
            assert (await c.get(path)).status_code == 401, path
