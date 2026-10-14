"""Build a PlanningInput straight from a case spec, without a database.

Unit tests use this to run the pure core on every case; the loader test checks that seeding and
loading from the database produces exactly the same input.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from app.modules.planning.schemas import InboundPo, PlanningInput
from app.scenarios import scenario1 as s1
from app.scenarios.types import FORECAST_HORIZON_DAYS, CaseSpec, sales_series
from app.shared.enums import PoStatus

DEFAULT_ORDER_CYCLE_DAYS = 7
OPEN_PO_STATUSES = frozenset({PoStatus.PLACED, PoStatus.CONFIRMED})


def _zone_other_load(case: CaseSpec, lead: int) -> Decimal:
    """Projected volume at our arrival of every other SKU seeded in the same node and zone.

    That is the case's declared neighbours plus other cases' SKUs that happen to share the zone.
    """
    zone = s1.PRODUCTS[case.sku].zone
    stocks: dict[str, int] = {}
    for n in case.zone_neighbours:
        stocks[n.sku] = n.on_hand - n.forecast_daily * lead
    for other in s1.CASES:
        if other.node != case.node or other.sku == case.sku:
            continue
        if s1.PRODUCTS[other.sku].zone != zone:
            continue
        inbound = sum(
            po.qty
            for po in other.open_pos
            if po.status in OPEN_PO_STATUSES and 0 <= po.eta_offset <= lead
        )
        stocks[other.sku] = other.on_hand + inbound - (other.forecast_daily or 0) * lead
    return sum(
        (max(Decimal(0), Decimal(q)) * s1.PRODUCTS[sku].unit_volume for sku, q in stocks.items()),
        Decimal(0),
    )


def planning_input_from_case(case: CaseSpec, today: date, now: datetime) -> PlanningInput:
    p = s1.PRODUCTS[case.sku]
    supplier = s1.SUPPLIERS[p.supplier]
    amount, committed = s1.BUDGETS.get((case.node, p.category), (s1.DEFAULT_BUDGET_INR, Decimal(0)))
    lead = p.lead_time_days
    other_load = _zone_other_load(case, lead)
    return PlanningInput(
        sku=case.sku,
        node=case.node,
        category=p.category,
        today=today,
        rec_qty=case.rec,
        supplier_code=p.supplier,
        supplier_active=supplier.active,
        unit_cost_inr=p.unit_cost_inr,
        moq=p.moq,
        case_pack=p.case_pack,
        lead_time_days=lead,
        order_cycle_days=p.order_cycle_days or DEFAULT_ORDER_CYCLE_DAYS,
        on_hand=case.on_hand,
        reserved=case.reserved,
        snapshot_as_of=now - timedelta(hours=case.snapshot_age_hours),
        forecast=(
            ()
            if case.forecast_daily is None
            else (float(case.forecast_daily),) * FORECAST_HORIZON_DAYS
        ),
        sales=() if case.sales_mean is None else sales_series(case.sales_mean, case.sales_sigma),
        inbound=tuple(
            InboundPo(po_number=f"S1-{case.id}-{i}", qty=po.qty, eta_offset=po.eta_offset)
            for i, po in enumerate(case.open_pos, start=1)
            if po.status in OPEN_PO_STATUSES
        ),
        budget_remaining_inr=max(Decimal(0), amount - committed),
        zone_capacity=s1.ZONE_CAPACITY.get((case.node, p.zone), s1.DEFAULT_ZONE_CAPACITY),
        zone_other_load=other_load,
        unit_volume=p.unit_volume,
        perishable=p.perishable,
        shelf_life_days=p.shelf_life_days,
        supplier_notes=supplier.notes,
        product_notes=p.notes,
    )
