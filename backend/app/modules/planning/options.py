"""Resolution options when the need cannot be met within the hard constraints (KB §7.3).

One builder per binding constraint (dict dispatch). Each option says what a human must approve,
and its quantity respects every other cap, so approving that one thing makes it valid.
"""

from collections.abc import Callable

from app.modules.planning.schemas import PlanningInput, ResolutionOption
from app.shared.enums import ConstraintCode
from app.shared.money import format_inr
from app.shared.rounding import floor_to_case

Builder = Callable[[PlanningInput, int, dict[ConstraintCode, int]], list[ResolutionOption]]


def _others(caps: dict[ConstraintCode, int], skip: ConstraintCode) -> int | None:
    rest = [v for k, v in caps.items() if k is not skip]
    return min(rest) if rest else None


def _budget(
    inp: PlanningInput, need: int, caps: dict[ConstraintCode, int]
) -> list[ResolutionOption]:
    qty = need if (o := _others(caps, ConstraintCode.BUDGET)) is None else min(need, o)
    qty = max(floor_to_case(qty, inp.case_pack), inp.moq)
    extra = qty * inp.unit_cost_inr - inp.budget_remaining_inr
    out = [
        ResolutionOption(
            kind="raise_budget",
            qty=qty,
            requires=f"budget increase of {format_inr(extra)}",
            description=f"Order {qty} if the {inp.category} budget grows by {format_inr(extra)}.",
        )
    ]
    cap = caps[ConstraintCode.BUDGET]
    if 0 < cap < inp.moq:
        out.append(
            ResolutionOption(
                kind="waive_moq",
                qty=cap,
                requires=f"supplier accepts {cap} below MOQ {inp.moq}",
                description=f"Order {cap} (what the budget allows) if the supplier waives the MOQ.",
            )
        )
    return out


def _storage(
    inp: PlanningInput, need: int, caps: dict[ConstraintCode, int]
) -> list[ResolutionOption]:
    now = caps[ConstraintCode.STORAGE]
    return (
        [
            ResolutionOption(
                kind="split_delivery",
                qty=need,
                requires="a second delivery slot",
                description=f"Deliver {now} now and {need - now} once sales free the space.",
            )
        ]
        if now >= inp.moq
        else [
            ResolutionOption(
                kind="free_storage",
                qty=need,
                requires=f"{need - now} units of extra space in {inp.node}",
                description="Free up zone space (or move stock) before ordering.",
            )
        ]
    )


def _shelf_life(
    inp: PlanningInput, need: int, caps: dict[ConstraintCode, int]
) -> list[ResolutionOption]:
    cap = caps[ConstraintCode.SHELF_LIFE]
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
    inp: PlanningInput, need_qty: int, caps: dict[ConstraintCode, int]
) -> tuple[ResolutionOption, ...]:
    """Options for each cap that blocks the need, tightest first."""
    binding = sorted((v, k) for k, v in caps.items() if v < need_qty)
    return tuple(o for _, code in binding for o in BUILDERS[code](inp, need_qty, caps))
