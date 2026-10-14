"""Resolution options when the need cannot be met within the hard constraints (KB §7.3).

One builder per binding constraint (dict dispatch). Each option says what a human must approve,
and its quantity is case-valid, meets the MOQ and respects every other cap, so approving that
one thing makes it valid. A builder offers nothing when no such quantity exists.
"""

from collections.abc import Callable

from app.modules.planning.schemas import PlanningInput, ResolutionOption
from app.shared.enums import ConstraintCode
from app.shared.money import format_inr
from app.shared.rounding import floor_to_case

Caps = dict[ConstraintCode, int]
Builder = Callable[[PlanningInput, int, Caps], list[ResolutionOption]]


def _within_others(inp: PlanningInput, need: int, caps: Caps, skip: ConstraintCode) -> int | None:
    """Largest valid quantity up to `need` that every cap except `skip` allows."""
    limit = min([need, *(v for k, v in caps.items() if k is not skip)])
    qty = floor_to_case(limit, inp.case_pack)
    return qty if qty >= inp.moq else None


def _budget(inp: PlanningInput, need: int, caps: Caps) -> list[ResolutionOption]:
    out = []
    qty = _within_others(inp, need, caps, ConstraintCode.BUDGET)
    if qty is not None and qty > caps[ConstraintCode.BUDGET]:
        extra = qty * inp.unit_cost_inr - inp.budget_remaining_inr
        out.append(
            ResolutionOption(
                kind="raise_budget",
                qty=qty,
                requires=f"budget increase of {format_inr(extra)}",
                description=f"Order {qty} if the budget grows by {format_inr(extra)}.",
            )
        )
    cap = floor_to_case(min(caps.values()), inp.case_pack)
    if 0 < cap < inp.moq:
        out.append(
            ResolutionOption(
                kind="waive_moq",
                qty=cap,
                requires=f"supplier accepts {cap} below MOQ {inp.moq}",
                description=f"Order {cap} (what the limits allow) if the supplier waives the MOQ.",
            )
        )
    return out


def _storage(inp: PlanningInput, need: int, caps: Caps) -> list[ResolutionOption]:
    qty = _within_others(inp, need, caps, ConstraintCode.STORAGE)
    now = caps[ConstraintCode.STORAGE]
    if qty is None or qty <= now:
        return []
    if now >= inp.moq:
        return [
            ResolutionOption(
                kind="split_delivery",
                qty=qty,
                requires="a second delivery slot",
                description=f"Deliver {now} now and {qty - now} once sales free the space.",
            )
        ]
    return [
        ResolutionOption(
            kind="free_storage",
            qty=qty,
            requires=f"{qty - now} units of extra space in {inp.node}",
            description="Free up zone space (or move stock) before ordering.",
        )
    ]


def _shelf_life(inp: PlanningInput, need: int, caps: Caps) -> list[ResolutionOption]:
    cap = floor_to_case(min(caps.values()), inp.case_pack)
    if cap < inp.moq:
        return []
    return [
        ResolutionOption(
            kind="order_more_often",
            qty=cap,
            requires="an extra order before the next cycle",
            description=f"Order {cap} now (what sells before expiry) and re-order sooner.",
        )
    ]


BUILDERS: dict[ConstraintCode, Builder] = {
    ConstraintCode.BUDGET: _budget,
    ConstraintCode.STORAGE: _storage,
    ConstraintCode.SHELF_LIFE: _shelf_life,
}


def resolution_options(
    inp: PlanningInput, need_qty: int, caps: Caps
) -> tuple[ResolutionOption, ...]:
    """Options for each cap that blocks the need, tightest first."""
    binding = sorted((v, k) for k, v in caps.items() if v < need_qty)
    return tuple(o for _, code in binding for o in BUILDERS[code](inp, need_qty, caps))
