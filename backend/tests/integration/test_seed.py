from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base
from app.models import (
    Budget,
    DemandForecast,
    ErpBehaviour,
    InventorySnapshot,
    Node,
    PoLine,
    Product,
    PurchaseOrder,
    Recommendation,
    SalesHistory,
    StorageZone,
)
from app.scenarios.scenario1 import BUDGETS, CASES, ZONE_CAPACITY
from app.seed.scenario1 import seed_scenario1
from app.shared.enums import PoStatus

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


async def _counts(session: AsyncSession) -> dict[str, int]:
    out = {}
    for table in Base.metadata.sorted_tables:
        out[table.name] = (
            await session.execute(select(func.count()).select_from(table))
        ).scalar_one()
    return out


async def _ids(session: AsyncSession, sku: str, node: str) -> tuple[int, int]:
    product_id = (await session.execute(select(Product.id).where(Product.sku == sku))).scalar_one()
    node_id = (await session.execute(select(Node.id).where(Node.code == node))).scalar_one()
    return product_id, node_id


async def _fingerprint(
    session: AsyncSession, today: date, now: datetime
) -> list[tuple[object, ...]]:
    """Case data expressed relative to today/now: must not depend on the seeding date."""
    rows: list[tuple[object, ...]] = []
    for case in CASES:
        product_id, node_id = await _ids(session, case.sku, case.node)
        where = (InventorySnapshot.product_id == product_id, InventorySnapshot.node_id == node_id)
        snap = (await session.execute(select(InventorySnapshot).where(*where))).scalar_one()
        forecasts = (
            await session.execute(
                select(DemandForecast.day, DemandForecast.qty)
                .where(DemandForecast.product_id == product_id, DemandForecast.node_id == node_id)
                .order_by(DemandForecast.day)
            )
        ).all()
        sales = (
            await session.execute(
                select(SalesHistory.day, SalesHistory.qty)
                .where(SalesHistory.product_id == product_id, SalesHistory.node_id == node_id)
                .order_by(SalesHistory.day)
            )
        ).all()
        lines = (
            await session.execute(
                select(PoLine.qty_ordered, PoLine.eta, PurchaseOrder.status)
                .join(PurchaseOrder)
                .where(PoLine.product_id == product_id, PurchaseOrder.node_id == node_id)
                .order_by(PoLine.eta, PoLine.qty_ordered)
            )
        ).all()
        rows.append(
            (
                case.id,
                snap.on_hand,
                snap.reserved,
                now - snap.as_of,
                tuple(((d - today).days, q) for d, q in forecasts),
                tuple(((d - today).days, q) for d, q in sales),
                tuple((q, (eta - today).days, s) for q, eta, s in lines),
            )
        )
    return rows


async def test_seed_writes_every_case(session: AsyncSession) -> None:
    await seed_scenario1(session, today=TODAY, now=NOW)

    for case in CASES:
        product_id, node_id = await _ids(session, case.sku, case.node)
        rec = (
            await session.execute(
                select(Recommendation).where(
                    Recommendation.product_id == product_id, Recommendation.node_id == node_id
                )
            )
        ).scalar_one()
        assert rec.qty == case.rec, case.id
        snap = (
            await session.execute(
                select(InventorySnapshot).where(
                    InventorySnapshot.product_id == product_id, InventorySnapshot.node_id == node_id
                )
            )
        ).scalar_one()
        assert (snap.on_hand, snap.reserved) == (case.on_hand, case.reserved), case.id
        assert NOW - snap.as_of == timedelta(hours=case.snapshot_age_hours), case.id


async def test_seed_writes_relative_series_and_pos(session: AsyncSession) -> None:
    await seed_scenario1(session, today=TODAY, now=NOW)
    by_id = {row[0]: row for row in await _fingerprint(session, TODAY, NOW)}

    c10 = by_id["C10"]
    assert c10[4][0] == (1, 40) and c10[4][-1] == (28, 40)  # forecast days 1..28
    assert c10[5][0] == (-28, 30) and c10[5][-1] == (-1, 50)  # sales days -28..-1
    assert c10[6] == ((60, -1, PoStatus.PLACED), (120, 2, PoStatus.PLACED))
    assert by_id["Q3a"][4] == () and len(by_id["Q3a"][5]) == 28
    assert by_id["Q3b"][4] == () and by_id["Q3b"][5] == ()


async def test_seed_writes_zones_budgets_and_erp_behaviours(session: AsyncSession) -> None:
    await seed_scenario1(session, today=TODAY, now=NOW)

    zones = {
        (code, z.zone): z.capacity_units
        for z, code in (await session.execute(select(StorageZone, Node.code).join(Node))).all()
    }
    for key, cap in ZONE_CAPACITY.items():
        assert zones[key] == cap
    budgets = {
        (code, b.category): (b.amount_inr, b.committed_inr, b.period)
        for b, code in (await session.execute(select(Budget, Node.code).join(Node))).all()
    }
    for key, (amount, committed) in BUDGETS.items():
        assert budgets[key] == (amount, committed, "2026-10")
    behaviours = {
        (b.node_code, b.sku): b.behaviour
        for b in (await session.execute(select(ErpBehaviour))).scalars()
    }
    assert behaviours == {(c.node, c.sku): c.erp.behaviour for c in CASES if c.erp}


async def test_seed_twice_is_idempotent(session: AsyncSession) -> None:
    await seed_scenario1(session, today=TODAY, now=NOW)
    first = await _counts(session)
    await seed_scenario1(session, today=TODAY, now=NOW)
    assert await _counts(session) == first


async def test_reseed_on_a_later_day_gives_the_same_relative_data(session: AsyncSession) -> None:
    await seed_scenario1(session, today=TODAY, now=NOW)
    before = await _fingerprint(session, TODAY, NOW)
    later, later_now = TODAY + timedelta(days=3), NOW + timedelta(days=3)
    await seed_scenario1(session, today=later, now=later_now)
    assert await _fingerprint(session, later, later_now) == before


async def test_reseed_removes_orders_placed_since(session: AsyncSession) -> None:
    """A PO created by an agent run must not leak into the next seeded run as inbound stock."""
    await seed_scenario1(session, today=TODAY, now=NOW)
    product_id, node_id = await _ids(session, "COKE-750", "BANDRA")
    supplier_id = (
        await session.execute(
            select(Recommendation.supplier_id).where(Recommendation.product_id == product_id)
        )
    ).scalar_one()
    po = PurchaseOrder(
        po_number="RUN-1",
        node_id=node_id,
        supplier_id=supplier_id,
        status=PoStatus.PLACED,
        created_at=NOW,
    )
    po.lines.append(
        PoLine(
            product_id=product_id, qty_ordered=800, unit_cost_inr=35, eta=TODAY + timedelta(days=3)
        )
    )
    session.add(po)
    await session.commit()

    await seed_scenario1(session, today=TODAY, now=NOW)
    assert (
        await session.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == "RUN-1"))
    ).scalar_one_or_none() is None
