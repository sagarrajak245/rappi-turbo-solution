"""Load everything the planning core needs for one SKU x node into a PlanningInput.

The one place planning reads other modules' tables. Everything after this is pure.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PlanningSettings
from app.core.errors import NotFound
from app.models import (
    Budget,
    DemandForecast,
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
from app.modules.planning.schemas import InboundPo, PlanningInput
from app.shared.enums import PoStatus

OPEN_PO_STATUSES = (PoStatus.PLACED, PoStatus.CONFIRMED)


async def _zone_other_load(
    session: AsyncSession, node: Node, product: Product, today: date, lead: int
) -> Decimal:
    """Projected volume of the zone's other SKUs when our order arrives (day `lead`)."""
    others = (
        await session.execute(
            select(InventorySnapshot, Product.unit_volume)
            .join(Product, InventorySnapshot.product_id == Product.id)
            .where(
                InventorySnapshot.node_id == node.id,
                Product.storage_zone == product.storage_zone,
                Product.id != product.id,
            )
            .order_by(InventorySnapshot.as_of)
        )
    ).all()
    latest = {snap.product_id: (snap.on_hand, volume) for snap, volume in others}
    if not latest:
        return Decimal(0)
    arrival = today + timedelta(days=lead)
    ids = list(latest)
    forecast_rows = (
        await session.execute(
            select(DemandForecast.product_id, func.sum(DemandForecast.qty))
            .where(
                DemandForecast.node_id == node.id,
                DemandForecast.product_id.in_(ids),
                DemandForecast.day > today,
                DemandForecast.day <= arrival,
            )
            .group_by(DemandForecast.product_id)
        )
    ).all()
    forecast = {pid: qty for pid, qty in forecast_rows}
    inbound: dict[int, int] = defaultdict(int)
    rows = await session.execute(
        select(PoLine.product_id, PoLine.qty_ordered - PoLine.qty_received)
        .join(PurchaseOrder)
        .where(
            PurchaseOrder.node_id == node.id,
            PurchaseOrder.status.in_(OPEN_PO_STATUSES),
            PoLine.product_id.in_(ids),
            PoLine.eta >= today,
            PoLine.eta <= arrival,
        )
    )
    for pid, qty in rows.all():
        inbound[pid] += qty
    total = Decimal(0)
    for pid, (on_hand, volume) in latest.items():
        projected = Decimal(on_hand + inbound[pid]) - Decimal(forecast.get(pid) or 0)
        total += max(Decimal(0), projected) * volume
    return total


async def load_planning_input(
    session: AsyncSession, sku: str, node_code: str, today: date, *, settings: PlanningSettings
) -> PlanningInput:
    product = (await session.execute(select(Product).filter_by(sku=sku))).scalar_one_or_none()
    node = (await session.execute(select(Node).filter_by(code=node_code))).scalar_one_or_none()
    if product is None or node is None:
        raise NotFound(f"Unknown SKU {sku} or node {node_code}")
    pair = {"node_id": node.id, "product_id": product.id}

    snap = (
        await session.execute(
            select(InventorySnapshot)
            .filter_by(**pair)
            .order_by(InventorySnapshot.as_of.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    rec = (
        await session.execute(
            select(Recommendation)
            .filter_by(**pair)
            .order_by(Recommendation.created_at.desc(), Recommendation.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snap is None or rec is None:
        raise NotFound(f"No stock snapshot or recommendation for {sku} at {node_code}")

    supplier, terms = (
        await session.execute(
            select(Supplier, SupplierProduct)
            .join(SupplierProduct, SupplierProduct.supplier_id == Supplier.id)
            .where(Supplier.id == rec.supplier_id, SupplierProduct.product_id == product.id)
        )
    ).one()

    forecast = (
        (
            await session.execute(
                select(DemandForecast.qty)
                .filter_by(**pair)
                .where(DemandForecast.day > today)
                .order_by(DemandForecast.day)
            )
        )
        .scalars()
        .all()
    )
    sales = (
        (
            await session.execute(
                select(SalesHistory.qty)
                .filter_by(**pair)
                .where(
                    SalesHistory.day >= today - timedelta(days=settings.sales_window_days),
                    SalesHistory.day < today,
                )
                .order_by(SalesHistory.day)
            )
        )
        .scalars()
        .all()
    )
    inbound = (
        await session.execute(
            select(PurchaseOrder.po_number, PoLine.qty_ordered - PoLine.qty_received, PoLine.eta)
            .join(PurchaseOrder)
            .where(
                PurchaseOrder.node_id == node.id,
                PurchaseOrder.status.in_(OPEN_PO_STATUSES),
                PoLine.product_id == product.id,
            )
            .order_by(PurchaseOrder.po_number)
        )
    ).all()
    budget = (
        await session.execute(
            select(Budget).filter_by(
                node_id=node.id, category=product.category, period=today.strftime("%Y-%m")
            )
        )
    ).scalar_one_or_none()
    zone = (
        await session.execute(
            select(StorageZone).filter_by(node_id=node.id, zone=product.storage_zone)
        )
    ).scalar_one_or_none()

    lead = terms.lead_time_days
    return PlanningInput(
        sku=sku,
        node=node_code,
        category=product.category,
        today=today,
        rec_qty=rec.qty,
        supplier_code=supplier.code,
        supplier_active=supplier.active,
        unit_cost_inr=terms.unit_cost_inr,
        moq=terms.moq,
        case_pack=terms.case_pack,
        lead_time_days=lead,
        order_cycle_days=terms.order_cycle_days or settings.order_cycle_days,
        on_hand=snap.on_hand,
        reserved=snap.reserved,
        snapshot_as_of=snap.as_of,
        forecast=tuple(float(q) for q in forecast),
        sales=tuple(sales),
        inbound=tuple(
            InboundPo(po_number=number, qty=qty, eta_offset=(eta - today).days)
            for number, qty, eta in inbound
        ),
        budget_remaining_inr=(
            Decimal(0)
            if budget is None
            else max(Decimal(0), budget.amount_inr - budget.committed_inr)
        ),
        zone_capacity=None if zone is None else zone.capacity_units,
        zone_other_load=await _zone_other_load(session, node, product, today, lead),
        unit_volume=product.unit_volume,
        perishable=product.perishable,
        shelf_life_days=product.shelf_life_days,
        supplier_notes=supplier.notes,
        product_notes=product.notes,
    )
