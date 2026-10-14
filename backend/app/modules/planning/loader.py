"""Load everything the planning core needs for one SKU x node into a PlanningInput.

The one place planning reads other modules' tables (via the repository). Everything after
this is pure.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PlanningSettings
from app.core.errors import NotFound
from app.models import Node, Product
from app.modules.planning import repository as repo
from app.modules.planning.schemas import InboundPo, PlanningInput


async def _zone_other_load(
    session: AsyncSession, node: Node, product: Product, today: date, lead: int
) -> Decimal:
    """Projected volume of the zone's other SKUs when our order arrives (day `lead`)."""
    others = await repo.list_zone_other_snapshots(
        session, node.id, product.storage_zone, product.id
    )
    latest = {snap.product_id: (snap.on_hand, volume) for snap, volume in others}
    if not latest:
        return Decimal(0)
    arrival = today + timedelta(days=lead)
    ids = list(latest)
    forecast_rows = await repo.list_forecast_totals(session, node.id, ids, today, arrival)
    forecast = {pid: qty for pid, qty in forecast_rows}
    inbound: dict[int, int] = defaultdict(int)
    for pid, qty in await repo.list_open_po_qtys(session, node.id, ids, today, arrival):
        inbound[pid] += qty
    total = Decimal(0)
    for pid, (on_hand, volume) in latest.items():
        projected = Decimal(on_hand + inbound[pid]) - Decimal(forecast.get(pid) or 0)
        total += max(Decimal(0), projected) * volume
    return total


async def load_planning_input(
    session: AsyncSession, sku: str, node_code: str, today: date, *, settings: PlanningSettings
) -> PlanningInput:
    product = await repo.get_product_by_sku(session, sku)
    node = await repo.get_node_by_code(session, node_code)
    if product is None or node is None:
        raise NotFound(f"Unknown SKU {sku} or node {node_code}")

    snap = await repo.get_latest_snapshot(session, node.id, product.id)
    rec = await repo.get_latest_recommendation(session, node.id, product.id)
    if snap is None or rec is None:
        raise NotFound(f"No stock snapshot or recommendation for {sku} at {node_code}")

    supplier, terms = await repo.get_supplier_terms(session, rec.supplier_id, product.id)
    forecast = await repo.list_forecast_qtys_after(session, node.id, product.id, today)
    sales = await repo.list_sales_qtys(
        session,
        node.id,
        product.id,
        today - timedelta(days=settings.sales_window_days),
        today,
    )
    inbound = await repo.list_open_inbound(session, node.id, product.id)
    budget = await repo.get_budget(session, node.id, product.category, today.strftime("%Y-%m"))
    zone = await repo.get_storage_zone(session, node.id, product.storage_zone)

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
