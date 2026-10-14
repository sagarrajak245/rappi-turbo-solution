"""Seed Scenario 1 from the case table.

Replace, not upsert: catalog rows (nodes, suppliers, products, terms) are upserted by natural key,
but every row tied to a scenario SKU x node pair (stock, sales, forecasts, recommendations, open
POs including ones created by earlier agent runs, mock-ERP orders and behaviours) is deleted and
written again, in one transaction. Dates are relative to `today`, so re-seeding on another day
reproduces the same decisions.

This is a tool, like Alembic, so it writes every module's tables directly.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Budget,
    DemandForecast,
    ErpBehaviour,
    ErpPurchaseOrder,
    ErpRequest,
    InventorySnapshot,
    Node,
    PoLine,
    Product,
    PurchaseOrder,
    Recommendation,
    SalesHistory,
    StorageZone,
    Supplier,
    SupplierProduct,
)
from app.scenarios import scenario1 as s1
from app.scenarios.types import FORECAST_HORIZON_DAYS, SALES_WINDOW_DAYS, CaseSpec, sales_series

NEIGHBOUR_SNAPSHOT_AGE = timedelta(hours=2)


async def _upsert[M](
    session: AsyncSession, model: type[M], keys: dict[str, Any], **values: Any
) -> M:
    row = (await session.execute(select(model).filter_by(**keys))).scalar_one_or_none()
    if row is None:
        row = model(**keys, **values)
        session.add(row)
    else:
        for name, value in values.items():
            setattr(row, name, value)
    return row


async def _catalog(
    session: AsyncSession,
) -> tuple[dict[str, Node], dict[str, Product], dict[str, Supplier]]:
    nodes = {
        code: await _upsert(session, Node, {"code": code}, name=name, city=s1.CITY)
        for code, name in s1.NODES.items()
    }
    suppliers = {
        code: await _upsert(
            session, Supplier, {"code": code}, name=s.name, active=s.active, notes=s.notes
        )
        for code, s in s1.SUPPLIERS.items()
    }
    products = {}
    for sku, p in s1.PRODUCTS.items():
        products[sku] = await _upsert(
            session,
            Product,
            {"sku": sku},
            name=p.name,
            category=p.category,
            storage_zone=p.zone,
            perishable=p.perishable,
            shelf_life_days=p.shelf_life_days,
            unit_volume=p.unit_volume,
            notes=p.notes,
        )
    await session.flush()
    for sku, p in s1.PRODUCTS.items():
        await _upsert(
            session,
            SupplierProduct,
            {"supplier_id": suppliers[p.supplier].id, "product_id": products[sku].id},
            unit_cost_inr=p.unit_cost_inr,
            moq=p.moq,
            case_pack=p.case_pack,
            lead_time_days=p.lead_time_days,
            order_cycle_days=p.order_cycle_days,
            active=True,
        )
    return nodes, products, suppliers


async def _clear_pair(session: AsyncSession, node: Node, product: Product) -> None:
    pair = {"node_id": node.id, "product_id": product.id}
    for model in (InventorySnapshot, SalesHistory, DemandForecast, Recommendation):
        await session.execute(delete(model).filter_by(**pair))
    po_ids = (
        (
            await session.execute(
                select(PoLine.po_id)
                .join(PurchaseOrder)
                .where(PurchaseOrder.node_id == node.id, PoLine.product_id == product.id)
            )
        )
        .scalars()
        .all()
    )
    if po_ids:
        await session.execute(delete(PoLine).where(PoLine.po_id.in_(po_ids)))
        await session.execute(delete(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids)))
    erp_pair = {"node_code": node.code, "sku": product.sku}
    await session.execute(delete(ErpPurchaseOrder).filter_by(**erp_pair))
    await session.execute(delete(ErpBehaviour).filter_by(**erp_pair))


def _case_rows(
    case: CaseSpec, node: Node, product: Product, supplier: Supplier, today: date, now: datetime
) -> list[object]:
    pair = {"node_id": node.id, "product_id": product.id}
    rows: list[object] = [
        InventorySnapshot(
            **pair,
            on_hand=case.on_hand,
            reserved=case.reserved,
            as_of=now - timedelta(hours=case.snapshot_age_hours),
        ),
        Recommendation(
            **pair, supplier_id=supplier.id, qty=case.rec, source=s1.REC_SOURCE, created_at=now
        ),
    ]
    if case.forecast_daily is not None:
        rows += [
            DemandForecast(**pair, day=today + timedelta(days=d), qty=Decimal(case.forecast_daily))
            for d in range(1, FORECAST_HORIZON_DAYS + 1)
        ]
    if case.sales_mean is not None:
        series = sales_series(case.sales_mean, case.sales_sigma)
        rows += [
            SalesHistory(**pair, day=today - timedelta(days=SALES_WINDOW_DAYS - i), qty=qty)
            for i, qty in enumerate(series)
        ]
    cost = s1.PRODUCTS[case.sku].unit_cost_inr
    for i, po_spec in enumerate(case.open_pos, start=1):
        po = PurchaseOrder(
            po_number=f"S1-{case.id}-{i}",
            node_id=node.id,
            supplier_id=supplier.id,
            status=po_spec.status,
            created_at=now - timedelta(days=7),
        )
        po.lines.append(
            PoLine(
                product_id=product.id,
                qty_ordered=po_spec.qty,
                unit_cost_inr=cost,
                eta=today + timedelta(days=po_spec.eta_offset),
            )
        )
        rows.append(po)
    if case.erp is not None:
        rows.append(
            ErpBehaviour(
                node_code=node.code,
                sku=product.sku,
                behaviour=case.erp.behaviour,
                params=dict(case.erp.params),
                times_fired=0,
            )
        )
    return rows


async def seed_scenario1(session: AsyncSession, *, today: date, now: datetime) -> dict[str, int]:
    """Write Scenario 1 and commit. Returns how many cases and neighbour SKUs were seeded."""
    nodes, products, suppliers = await _catalog(session)

    pairs = {(c.node, c.sku) for c in s1.CASES}
    pairs |= {(c.node, n.sku) for c in s1.CASES for n in c.zone_neighbours}
    for node_code, sku in sorted(pairs):
        await _clear_pair(session, nodes[node_code], products[sku])
    # The mock ERP's idempotency ledger has no SKU x node, and the seed is local-only, so clear it
    # whole: otherwise a replayed key could return a response for an order deleted above.
    await session.execute(delete(ErpRequest))

    period = today.strftime("%Y-%m")
    for node_code, sku in sorted(pairs):
        p = s1.PRODUCTS[sku]
        zone_cap = s1.ZONE_CAPACITY.get((node_code, p.zone), s1.DEFAULT_ZONE_CAPACITY)
        await _upsert(
            session,
            StorageZone,
            {"node_id": nodes[node_code].id, "zone": p.zone},
            capacity_units=zone_cap,
        )
        amount, committed = s1.BUDGETS.get(
            (node_code, p.category), (s1.DEFAULT_BUDGET_INR, Decimal(0))
        )
        await _upsert(
            session,
            Budget,
            {"node_id": nodes[node_code].id, "category": p.category, "period": period},
            amount_inr=amount,
            committed_inr=committed,
        )

    for case in s1.CASES:
        node, product = nodes[case.node], products[case.sku]
        supplier = suppliers[s1.PRODUCTS[case.sku].supplier]
        session.add_all(_case_rows(case, node, product, supplier, today, now))
        for n in case.zone_neighbours:
            pair = {"node_id": node.id, "product_id": products[n.sku].id}
            session.add(
                InventorySnapshot(
                    **pair, on_hand=n.on_hand, reserved=0, as_of=now - NEIGHBOUR_SNAPSHOT_AGE
                )
            )
            session.add_all(
                DemandForecast(**pair, day=today + timedelta(days=d), qty=Decimal(n.forecast_daily))
                for d in range(1, FORECAST_HORIZON_DAYS + 1)
            )

    await session.commit()
    return {"cases": len(s1.CASES), "pairs": len(pairs)}
