"""Policy registries (KB D18).

HARD constraints are checked by planning.constraints.check_hard and can never be overridden.
SOFT policies are checks a decision may break only with an explicit, recorded override reason.
Each soft check returns a message when breached, else None (dict dispatch by policy name).
"""

from collections.abc import Callable

from app.core.config import PlanningSettings
from app.modules.planning.schemas import CalcResult, PlanningInput
from app.shared.enums import ConstraintCode

HARD: frozenset[str] = frozenset(c.value for c in ConstraintCode)

SoftCheck = Callable[[int, PlanningInput, CalcResult, PlanningSettings], str | None]


def _max_cover(qty: int, inp: PlanningInput, calc: CalcResult, s: PlanningSettings) -> str | None:
    if calc.demand_daily <= 0:
        return None
    cover = round((max(0.0, calc.stock_at_arrival) + qty) / calc.demand_daily, 9)
    if cover > s.max_cover_days:
        return f"{cover:.1f} days of cover exceeds the {s.max_cover_days}-day maximum"
    return None


def _max_deviation(
    qty: int, inp: PlanningInput, calc: CalcResult, s: PlanningSettings
) -> str | None:
    """Only the agent's own deviation counts: the calculated baseline is always allowed."""
    if inp.rec_qty <= 0 or qty == calc.qty:
        return None
    dev = round(abs(qty - inp.rec_qty) / inp.rec_qty, 9)
    if dev > s.max_deviation_from_rec_pct:
        return f"{dev:.0%} away from the recommendation (max {s.max_deviation_from_rec_pct:.0%})"
    return None


SOFT: dict[str, SoftCheck] = {
    "max_cover_days": _max_cover,
    "max_deviation_from_rec": _max_deviation,
}
