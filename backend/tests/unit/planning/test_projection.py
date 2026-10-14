"""14-day stock projection behind the review chart, against a hand-worked case."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.config import get_settings
from app.modules.planning.schemas import InboundPo, PlanningInput
from app.modules.planning.service import calculate, project_stock

# available 90 (100 on hand - 10 reserved), 20/day demand, 30 inbound on day 2, lead 3 days
INP = PlanningInput(
    sku="SKU",
    node="NODE",
    category="cat",
    today=date(2026, 10, 14),
    rec_qty=60,
    supplier_code="SUP",
    supplier_active=True,
    unit_cost_inr=Decimal(10),
    moq=10,
    case_pack=10,
    lead_time_days=3,
    order_cycle_days=7,
    on_hand=100,
    reserved=10,
    snapshot_as_of=datetime(2026, 10, 14, 6, tzinfo=UTC),
    forecast=(20.0,) * 14,
    inbound=(InboundPo(po_number="PO1", qty=30, eta_offset=2),),
    budget_remaining_inr=Decimal(100_000),
    zone_capacity=Decimal(500),
    zone_other_load=Decimal(100),
    unit_volume=Decimal(2),
)


def test_no_order_runs_out_after_inbound_is_used() -> None:
    calc = calculate(INP, get_settings().planning)
    proj = project_stock(INP, calc, 60, days=10)
    assert proj.no_order.stock == (90, 70, 80, 60, 40, 20, 0, 0, 0, 0, 0)
    assert proj.no_order.stockout_day == 7  # day 6 ends at exactly 0; day 7 demand goes unmet


def test_order_lands_after_lead_time_and_pushes_the_stockout_out() -> None:
    calc = calculate(INP, get_settings().planning)
    proj = project_stock(INP, calc, 60, days=10)
    assert proj.agent.qty == 60
    assert proj.agent.stock == (90, 70, 80, 120, 100, 80, 60, 40, 20, 0, 0)
    assert proj.agent.stockout_day == 10
    assert proj.system.qty == calc.qty
    assert proj.storage_ceiling == 200  # (500 - 100) / 2


def test_defaults_to_14_days_and_no_ceiling_without_a_zone() -> None:
    inp = INP.model_copy(update={"zone_capacity": None})
    proj = project_stock(inp, calculate(inp, get_settings().planning), 0)
    assert len(proj.agent.stock) == 15
    assert proj.storage_ceiling is None
    assert proj.agent.stock == proj.no_order.stock


def test_stock_arriving_today_counts_on_day_zero() -> None:
    # The calculator treats eta_offset 0 inbound as usable; a same-day order is on the shelf too.
    inp = INP.model_copy(
        update={"inbound": (InboundPo(po_number="PO0", qty=30, eta_offset=0),), "lead_time_days": 0}
    )
    proj = project_stock(inp, calculate(inp, get_settings().planning), 60, days=2)
    assert proj.no_order.stock == (120, 100, 80)
    assert proj.agent.stock == (180, 160, 140)
