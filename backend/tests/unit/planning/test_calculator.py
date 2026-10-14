"""Calculator: the C10 worked example step by step, formula boundaries, and every case."""

from datetime import UTC, date, datetime

import pytest

from app.core.config import PlanningSettings
from app.modules.planning.calculator import calculate
from app.modules.planning.schemas import InboundPo, PlanningInput
from app.scenarios.inputs import planning_input_from_case
from app.scenarios.scenario1 import CASES, CASES_BY_ID
from app.shared.enums import ConstraintCode, FlagCode, Outcome, Verdict

TODAY = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)
SETTINGS = PlanningSettings()
CALC_FLAGS = {FlagCode.PARTIAL_COVERAGE, FlagCode.STOCKOUT_BEFORE_ARRIVAL}
# Cases whose baseline is decided by a blocking or escalating data-quality flag, not the calculator.
DQ_DECIDED = {"Q1", "Q2", "Q3b", "Q5", "Q6"}


def _input(case_id: str) -> PlanningInput:
    return planning_input_from_case(CASES_BY_ID[case_id], TODAY, NOW)


def test_worked_example_c10_step_by_step() -> None:
    r = calculate(_input("C10"), SETTINGS)
    assert r.protection_days == 11
    assert r.demand_daily == 40
    assert r.demand_source == "forecast"
    assert r.demand_over_p == 440
    assert r.safety_stock == 55
    assert r.target == 495
    assert r.inventory_position == 290  # 180 - 10 + 120; the overdue 60 is excluded
    assert r.need == 205
    assert r.need_qty == 210
    assert r.caps[ConstraintCode.BUDGET] == 620
    assert r.caps[ConstraintCode.STORAGE] == 540
    assert r.stock_at_arrival == 130
    assert (r.verdict, r.qty, r.outcome) == (Verdict.MODIFY, 210, Outcome.PROPOSE)
    assert r.cover_days == 8.5
    assert {f.code for f in r.flags} == set()


@pytest.mark.parametrize("case", [c for c in CASES if c.id not in DQ_DECIDED], ids=lambda c: c.id)
def test_case_baseline(case) -> None:  # type: ignore[no-untyped-def]
    r = calculate(planning_input_from_case(case, TODAY, NOW), SETTINGS)
    assert (r.verdict, r.qty, r.outcome) == (
        case.expected.verdict,
        case.expected.qty,
        case.expected.outcome,
    )
    assert {f.code for f in r.flags} == set(case.expected.flags) & CALC_FLAGS


def test_no_need_is_reject_zero() -> None:
    r = calculate(_input("C2"), SETTINGS)
    assert (r.need, r.need_qty, r.qty, r.verdict) == (0, 0, 0, Verdict.REJECT)


def test_need_below_moq_rounds_up_to_moq() -> None:
    assert calculate(_input("C5"), SETTINGS).need_qty == 150


def test_exact_case_multiple_is_not_bumped() -> None:
    # C1 + 3 units on hand: N = 1053 - 313 = 740 = 37 cases of 20 exactly.
    inp = _input("C1").model_copy(update={"on_hand": 333})
    assert calculate(inp, SETTINGS).need_qty == 740


def test_sales_fallback_when_no_forecast() -> None:
    r = calculate(_input("Q3a"), SETTINGS)
    assert (r.demand_source, r.demand_daily) == ("sales", 30)


def test_inbound_due_after_protection_period_is_ignored() -> None:
    late = InboundPo(po_number="X", qty=500, eta_offset=12)  # C3 has P = 12; 13 is outside
    inp = _input("C1").model_copy(update={"inbound": (late.model_copy(update={"eta_offset": 11}),)})
    assert calculate(inp, SETTINGS).inventory_position == 310 + 500
    inp = _input("C1").model_copy(update={"inbound": (late,)})
    assert calculate(inp, SETTINGS).inventory_position == 310


@pytest.mark.parametrize(("on_hand", "flagged"), [(320, False), (319, True)])
def test_stockout_before_arrival_boundary(on_hand: int, flagged: bool) -> None:
    # C1: available = on_hand - 20, demand until arrival (L3) = 300 -> S_arr 0 vs -1.
    r = calculate(_input("C1").model_copy(update={"on_hand": on_hand}), SETTINGS)
    assert (FlagCode.STOCKOUT_BEFORE_ARRIVAL in {f.code for f in r.flags}) is flagged


def test_c9_escalates_with_options() -> None:
    r = calculate(_input("C9"), SETTINGS)
    assert (r.qty, r.verdict, r.outcome) == (None, None, Outcome.ESCALATE)
    assert r.options
    assert all(o.requires for o in r.options)
