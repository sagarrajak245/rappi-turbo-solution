"""Inputs and outputs of the deterministic planning core. Pure data, no I/O.

PlanningInput is everything the calculator, data-quality checks and validator need for one
SKU x node, already fetched from the database (see loader.py). Day offsets are relative to
`today`: forecast[0] is tomorrow (day 1), sales[-1] is yesterday.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.shared.enums import ConstraintCode, FlagCode, FlagSeverity, Outcome, Verdict


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class InboundPo(_Frozen):
    """An open purchase-order line for this SKU x node (cancelled/received ones are excluded)."""

    po_number: str
    qty: int
    eta_offset: int  # days from today; negative = overdue


class PlanningInput(_Frozen):
    sku: str
    node: str
    category: str
    today: date
    rec_qty: int

    supplier_code: str
    supplier_active: bool
    unit_cost_inr: Decimal
    moq: int
    case_pack: int
    lead_time_days: int
    order_cycle_days: int

    on_hand: int
    reserved: int
    snapshot_as_of: datetime

    forecast: tuple[float, ...] = ()  # daily forecast for day 1, 2, ...
    sales: tuple[int, ...] = ()  # daily sales, oldest first, ending yesterday
    inbound: tuple[InboundPo, ...] = ()

    budget_remaining_inr: Decimal
    zone_capacity: Decimal | None = None  # None -> zone not modelled, no storage cap
    zone_other_load: Decimal = Decimal(0)  # other SKUs' projected volume at our arrival
    unit_volume: Decimal = Decimal(1)
    perishable: bool = False
    shelf_life_days: int | None = None

    # Free text from master data. Data, never instructions (Q7).
    supplier_notes: str | None = None
    product_notes: str | None = None


class Flag(_Frozen):
    code: FlagCode
    severity: FlagSeverity
    message: str


class Violation(_Frozen):
    """A broken hard constraint, machine-readable so the agent can explain and re-plan."""

    code: ConstraintCode
    qty: int
    limit: int
    message: str


class ResolutionOption(_Frozen):
    """A way out when the need cannot be met as is. Quantities are pre-checked against caps."""

    kind: str
    qty: int
    requires: str  # what a human must approve or change, "" when nothing
    description: str


class CalcResult(_Frozen):
    protection_days: int
    demand_daily: float
    demand_source: str  # "forecast" | "sales" | "none"
    demand_over_p: float
    safety_stock: int
    target: float
    inventory_position: int
    need: float
    need_qty: int  # need rounded up to MOQ and case pack (0 if no need)
    stock_at_arrival: float
    caps: dict[ConstraintCode, int]  # max qty allowed by each quantity cap
    qty: int | None  # baseline proposal; None when nothing valid can be proposed
    verdict: Verdict | None
    outcome: Outcome
    flags: tuple[Flag, ...] = ()
    cover_days: float | None = None
    options: tuple[ResolutionOption, ...] = ()


class ProjectionSeries(_Frozen):
    qty: int  # units ordered in this scenario (0 = no order)
    stock: tuple[float, ...]  # end-of-day stock for day 0 (today) .. day N
    stockout_day: int | None  # first day demand goes unmet, None if never


class StockProjection(_Frozen):
    no_order: ProjectionSeries
    system: ProjectionSeries
    agent: ProjectionSeries
    buyer: ProjectionSeries | None = None  # set once the buyer changes the quantity
    storage_ceiling: int | None  # units the zone holds for this SKU; None when not modelled
