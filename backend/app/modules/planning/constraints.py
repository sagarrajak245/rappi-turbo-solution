"""Hard constraints (KB D18), shared by the calculator, options and validator.

Caps are the largest quantity each limit allows, already floored to a case. A reason can never
override a hard constraint; only a human changing the input (budget, supplier terms) can.
"""

import math
from decimal import Decimal

from app.modules.planning.schemas import PlanningInput, Violation
from app.shared.enums import ConstraintCode
from app.shared.rounding import floor_to_case, safe_floor


def compute_caps(
    inp: PlanningInput,
    *,
    physical_at_arrival: float,
    sellable_after_arrival: float | None,
    stock_at_arrival: float,
) -> dict[ConstraintCode, int]:
    caps = {ConstraintCode.BUDGET: _budget_cap(inp)}
    if inp.zone_capacity is not None:
        free = (
            inp.zone_capacity - inp.zone_other_load - Decimal(physical_at_arrival) * inp.unit_volume
        )
        units = math.floor(max(Decimal(0), free) / inp.unit_volume)
        caps[ConstraintCode.STORAGE] = floor_to_case(units, inp.case_pack)
    if sellable_after_arrival is not None:
        room = max(0, safe_floor(sellable_after_arrival - max(0.0, stock_at_arrival)))
        caps[ConstraintCode.SHELF_LIFE] = floor_to_case(room, inp.case_pack)
    return caps


def _budget_cap(inp: PlanningInput) -> int:
    if inp.unit_cost_inr <= 0:
        raise ValueError(f"unit cost must be positive for {inp.sku}")
    return floor_to_case(math.floor(inp.budget_remaining_inr / inp.unit_cost_inr), inp.case_pack)


def check_hard(qty: int, inp: PlanningInput, caps: dict[ConstraintCode, int]) -> list[Violation]:
    """Every hard constraint `qty` breaks. Ordering nothing (0) breaks none."""
    if qty <= 0:
        return []
    out = []
    if qty < inp.moq:
        out.append(
            Violation(
                code=ConstraintCode.MOQ,
                qty=qty,
                limit=inp.moq,
                message=f"{qty} is below the supplier MOQ of {inp.moq}",
            )
        )
    if qty % inp.case_pack:
        out.append(
            Violation(
                code=ConstraintCode.CASE_PACK,
                qty=qty,
                limit=inp.case_pack,
                message=f"{qty} is not a multiple of the case pack {inp.case_pack}",
            )
        )
    for code, cap in caps.items():
        if qty > cap:
            out.append(
                Violation(
                    code=code,
                    qty=qty,
                    limit=cap,
                    message=f"{qty} exceeds the {code.value} limit of {cap}",
                )
            )
    return out


def nearest_case_qtys(qty: int, inp: PlanningInput) -> tuple[int, ...]:
    """Case-valid quantities either side of `qty` that also meet the MOQ (X2: 805 -> 768/816)."""
    down = floor_to_case(qty, inp.case_pack)
    up = down if down == qty else down + inp.case_pack
    return tuple(sorted({q for q in (down, up) if q >= inp.moq}))
