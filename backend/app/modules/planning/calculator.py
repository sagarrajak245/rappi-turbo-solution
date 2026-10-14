"""Deterministic baseline order quantity and verdict (KB §7.1 and §7.1a rulings).

    P    = lead time L + order cycle R             (protection period)
    D_P  = forecast over days 1..P                 (sales average if there is no forecast)
    SS   = ceil(z * sigma_daily * sqrt(P))         (sigma = population stdev of 28-day sales)
    IP   = on_hand - reserved + open POs due in [0, P]   (overdue POs are not counted)
    N    = max(0, D_P + SS - IP)
    Qn   = N rounded up to MOQ, then to the case pack
    caps = budget, storage at arrival, shelf life  (each floored to a case)

Verdict: Qn = 0 -> REJECT (or ACCEPT if rec is 0); Qn within caps -> ACCEPT if rec is feasible
and within max(1 case, 10% of rec) of Qn, else MODIFY; Qn over a cap -> MODIFY to the cap with
partial coverage if the cap still meets the MOQ, else ESCALATE with resolution options.
Data-quality flags are applied on top of this by the validator.
"""

import math
import statistics

from app.core.config import PlanningSettings
from app.modules.planning.constraints import compute_caps
from app.modules.planning.options import resolution_options
from app.modules.planning.schemas import CalcResult, Flag, PlanningInput, ResolutionOption
from app.shared.enums import FlagCode, FlagSeverity, Outcome, Verdict
from app.shared.rounding import ceil_to_case, safe_ceil


class _Demand:
    """Daily demand from the forecast, or the sales average when no forecast exists."""

    def __init__(self, inp: PlanningInput) -> None:
        self.forecast = inp.forecast
        self.fallback = statistics.fmean(inp.sales) if inp.sales else 0.0
        self.source = "forecast" if inp.forecast else ("sales" if inp.sales else "none")

    def over(self, first_day: int, last_day: int) -> float:
        """Total demand for days first_day..last_day (day 1 = tomorrow), inclusive."""
        days = range(first_day, last_day + 1)
        if not self.forecast:
            return self.fallback * len(days)
        return sum(
            self.forecast[d - 1] if d <= len(self.forecast) else self.forecast[-1] for d in days
        )


def _qty_for_need(need: float, inp: PlanningInput) -> int:
    if need <= 0:
        return 0
    return ceil_to_case(max(safe_ceil(need), inp.moq), inp.case_pack)


def calculate(inp: PlanningInput, settings: PlanningSettings) -> CalcResult:
    lead = inp.lead_time_days
    p = lead + inp.order_cycle_days
    demand = _Demand(inp)
    d_p = demand.over(1, p)
    d_l = demand.over(1, lead)
    sigma = statistics.pstdev(inp.sales) if len(inp.sales) > 1 else 0.0
    ss = safe_ceil(settings.z * sigma * math.sqrt(p))

    available = inp.on_hand - inp.reserved
    usable = sum(po.qty for po in inp.inbound if 0 <= po.eta_offset <= p)
    before_arrival = sum(po.qty for po in inp.inbound if 0 <= po.eta_offset <= lead)
    ip = available + usable
    target = d_p + ss
    need = round(max(0.0, target - ip), 9)
    need_qty = _qty_for_need(need, inp)

    stock_at_arrival = round(available + before_arrival - d_l, 9)
    physical_at_arrival = max(0.0, inp.on_hand + before_arrival - d_l)
    sellable = None
    if inp.shelf_life_days is not None:
        sellable = demand.over(
            lead + 1, lead + inp.shelf_life_days - settings.shelf_life_safety_days
        )
    caps = compute_caps(
        inp,
        physical_at_arrival=physical_at_arrival,
        sellable_after_arrival=sellable,
        stock_at_arrival=stock_at_arrival,
    )
    max_qty = min(caps.values())

    flags: list[Flag] = []
    if stock_at_arrival < 0:
        flags.append(
            Flag(
                code=FlagCode.STOCKOUT_BEFORE_ARRIVAL,
                severity=FlagSeverity.WARNING,
                message=f"Stock runs out {-stock_at_arrival:g} units before the order arrives",
            )
        )

    qty: int | None
    verdict: Verdict | None
    outcome = Outcome.PROPOSE
    options: tuple[ResolutionOption, ...] = ()
    if need_qty == 0:
        qty, verdict = 0, (Verdict.REJECT if inp.rec_qty > 0 else Verdict.ACCEPT)
    elif need_qty <= max_qty:
        qty, verdict = need_qty, Verdict.MODIFY
        rec = inp.rec_qty
        feasible = rec > 0 and rec % inp.case_pack == 0 and inp.moq <= rec <= max_qty
        if feasible and abs(rec - need_qty) <= max(
            inp.case_pack, settings.accept_tolerance_pct * rec
        ):
            qty, verdict = rec, Verdict.ACCEPT
    elif max_qty >= inp.moq and max_qty > 0:
        qty, verdict = max_qty, Verdict.MODIFY
        flags.append(
            Flag(
                code=FlagCode.PARTIAL_COVERAGE,
                severity=FlagSeverity.WARNING,
                message=f"Caps allow {max_qty} of the {need_qty} needed",
            )
        )
        options = resolution_options(inp, need_qty, caps)
    else:
        qty, verdict, outcome = None, None, Outcome.ESCALATE
        options = resolution_options(inp, need_qty, caps)

    daily = d_p / p
    cover = (
        None if qty is None or daily <= 0 else round((max(0.0, stock_at_arrival) + qty) / daily, 9)
    )
    return CalcResult(
        protection_days=p,
        demand_daily=round(daily, 9),
        demand_source=demand.source,
        demand_over_p=round(d_p, 9),
        safety_stock=ss,
        target=round(target, 9),
        inventory_position=ip,
        need=need,
        need_qty=need_qty,
        stock_at_arrival=stock_at_arrival,
        caps=caps,
        qty=qty,
        verdict=verdict,
        outcome=outcome,
        flags=tuple(flags),
        cover_days=cover,
        options=options,
    )
