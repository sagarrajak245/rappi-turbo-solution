"""Day-by-day stock projection for the review chart: no order vs the system qty vs the agent qty.

Day 0 is today's available stock (on hand - reserved) plus anything arriving today. Each later day
adds what arrives that day (open POs at their ETA, the new order at the lead time), then sells that
day's demand. Unmet
demand is lost, so stock never goes below 0; the first day demand goes unmet is the stockout.
"""

import math
from decimal import Decimal

from app.modules.planning.calculator import _Demand
from app.modules.planning.schemas import (
    CalcResult,
    PlanningInput,
    ProjectionSeries,
    StockProjection,
)


def _series(inp: PlanningInput, demand: _Demand, qty: int, days: int) -> ProjectionSeries:
    def arriving(day: int) -> int:
        landed = sum(po.qty for po in inp.inbound if po.eta_offset == day)
        return landed + (qty if day == inp.lead_time_days else 0)

    stock = float(inp.on_hand - inp.reserved + arriving(0))
    points = [round(max(0.0, stock), 3)]
    stockout = None
    for day in range(1, days + 1):
        stock += arriving(day)
        stock -= demand.over(day, day)
        if stock < 0:
            stockout = stockout or day
            stock = 0.0
        points.append(round(stock, 3))
    return ProjectionSeries(qty=qty, stock=tuple(points), stockout_day=stockout)


def project_stock(
    inp: PlanningInput,
    calc: CalcResult,
    qty: int,
    days: int = 14,
    buyer_qty: int | None = None,
) -> StockProjection:
    demand = _Demand(inp)
    ceiling = None
    if inp.zone_capacity is not None:
        free = max(Decimal(0), inp.zone_capacity - inp.zone_other_load)
        ceiling = math.floor(free / inp.unit_volume)
    return StockProjection(
        no_order=_series(inp, demand, 0, days),
        system=_series(inp, demand, calc.qty or 0, days),
        agent=_series(inp, demand, qty, days),
        buyer=None if buyer_qty is None else _series(inp, demand, buyer_qty, days),
        storage_ceiling=ceiling,
    )
