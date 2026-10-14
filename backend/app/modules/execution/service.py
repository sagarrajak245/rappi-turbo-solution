"""Execute an approved order against the ERP and verify the outcome (KB §3.2 nodes 11-15, D21).

Draft -> re-read & verify -> handle deviation -> submit -> re-read & verify. Every ERP call is
keyed by the proposal id, so running the same approved order twice never creates a second PO.
Nothing after submit is ever cancelled automatically: that needs a human.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ErpTimeout
from app.modules.erp_mock import service as erp
from app.modules.erp_mock.schemas import ErpDraftRequest, ErpPurchaseOrderOut
from app.modules.execution.schemas import (
    ApprovedOrder,
    Deviation,
    ExecutionResult,
    ExecutionStatus,
    Severity,
)
from app.modules.execution.verify import compare
from app.modules.planning import service as planning
from app.modules.planning.schemas import CalcResult
from app.shared.enums import ErpPoStatus, FlagCode

logger = logging.getLogger(__name__)


class _Ctx:
    """One execution: the order, its ERP calls and what was observed along the way."""

    def __init__(
        self, session: AsyncSession, order: ApprovedOrder, today: date, now: datetime, s: Settings
    ) -> None:
        self.session, self.order, self.today, self.now, self.s = session, order, today, now, s
        self.notes: list[str] = []

    def key(self, op: str) -> str:
        return f"{self.order.proposal_id}:{op}"

    def result(
        self,
        status: ExecutionStatus,
        po: ErpPurchaseOrderOut,
        deviations: tuple[Deviation, ...] = (),
        flags: tuple[FlagCode, ...] = (),
        replan: CalcResult | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            erp_number=po.erp_number,
            final_status=po.status,
            deviations=deviations,
            flags=flags,
            notes=tuple(self.notes),
            replan=replan,
        )

    async def cancel(self, po: ErpPurchaseOrderOut, why: str) -> ErpPurchaseOrderOut:
        self.notes.append(f"Draft {po.erp_number} cancelled: {why}")
        return await erp.cancel(self.session, po.erp_number, self.key("cancel"), self.now)


async def _create_draft(ctx: _Ctx) -> ErpPurchaseOrderOut:
    o = ctx.order
    req = ErpDraftRequest(
        node_code=o.node_code,
        sku=o.sku,
        supplier_code=o.supplier_code,
        qty=o.qty,
        case_pack=o.case_pack,
        unit_price_inr=o.unit_price_inr,
        eta=o.eta,
    )
    try:
        return await erp.create_draft(ctx.session, ctx.key("create"), req, ctx.now)
    except ErpTimeout:
        # The draft may exist. Retrying with the same key returns it instead of a duplicate (F3).
        ctx.notes.append("ERP timed out creating the draft; retried with the same key")
        logger.warning("erp create timed out", extra={"proposal_id": o.proposal_id})
        return await erp.create_draft(ctx.session, ctx.key("create"), req, ctx.now)


async def _replan(ctx: _Ctx, po: ErpPurchaseOrderOut) -> ExecutionResult:
    """Material change (price, case pack): the approved plan no longer holds."""
    devs = tuple(compare(ctx.order, po, ctx.s.erp))
    what = ", ".join(f"{d.field} {d.expected} -> {d.actual}" for d in devs)
    cancelled = await ctx.cancel(po, f"material change ({what})")
    if ctx.order.replans_done >= ctx.s.erp.max_replans:
        ctx.notes.append("Re-plan limit reached; escalating")
        return ctx.result(ExecutionStatus.ESCALATED, cancelled, deviations=devs)
    inp = await planning.load_planning_input(
        ctx.session, ctx.order.sku, ctx.order.node_code, ctx.today, settings=ctx.s.planning
    )
    changed = inp.model_copy(update={"unit_cost_inr": po.unit_price_inr, "case_pack": po.case_pack})
    calc = planning.calculate(changed, ctx.s.planning)
    ctx.notes.append(f"Re-planned with the ERP's terms: {calc.verdict} {calc.qty}; needs approval")
    return ctx.result(ExecutionStatus.REPLAN_REQUIRED, cancelled, deviations=devs, replan=calc)


async def _unfixable(ctx: _Ctx, po: ErpPurchaseOrderOut) -> ExecutionResult:
    devs = tuple(compare(ctx.order, po, ctx.s.erp))
    cancelled = await ctx.cancel(po, "the ERP draft does not match the approved order")
    return ctx.result(ExecutionStatus.ESCALATED, cancelled, deviations=devs)


# Worst severity among the draft's deviations -> what to do before submitting.
DraftHandler = Callable[[_Ctx, ErpPurchaseOrderOut], Awaitable[ExecutionResult]]
DRAFT_HANDLERS: dict[Severity, DraftHandler] = {
    Severity.UNFIXABLE: _unfixable,
    Severity.MATERIAL: _replan,
}
_RANK = {Severity.MINOR: 0, Severity.MATERIAL: 1, Severity.UNFIXABLE: 2}


async def _late_arrival_flags(ctx: _Ctx, po: ErpPurchaseOrderOut) -> tuple[FlagCode, ...]:
    """A later ETA is accepted with a note, but recompute whether we now stock out first (F5)."""
    inp = await planning.load_planning_input(
        ctx.session, ctx.order.sku, ctx.order.node_code, ctx.today, settings=ctx.s.planning
    )
    late = inp.model_copy(update={"lead_time_days": max(0, (po.eta - ctx.today).days)})
    calc = planning.calculate(late, ctx.s.planning)
    ctx.notes.append(f"ETA moved to {po.eta}; stock at arrival {calc.stock_at_arrival:.0f}")
    return tuple(f.code for f in calc.flags if f.code is FlagCode.STOCKOUT_BEFORE_ARRIVAL)


async def execute(
    session: AsyncSession, order: ApprovedOrder, today: date, now: datetime, settings: Settings
) -> ExecutionResult:
    ctx = _Ctx(session, order, today, now, settings)
    draft = await _create_draft(ctx)
    if draft.status is not ErpPoStatus.DRAFT and draft.status is not ErpPoStatus.SUBMITTED:
        ctx.notes.append(f"ERP holds the order as {draft.status}")
        return ctx.result(ExecutionStatus.ESCALATED, draft)

    draft = await erp.get(session, draft.erp_number)  # re-read, never trust the write response
    devs = compare(order, draft, settings.erp)
    worst = max((d.severity for d in devs), key=_RANK.__getitem__, default=None)
    if worst in DRAFT_HANDLERS:
        return await DRAFT_HANDLERS[worst](ctx, draft)
    flags = await _late_arrival_flags(ctx, draft) if devs else ()

    submitted = await erp.submit(session, draft.erp_number, ctx.key("submit"), now)
    if submitted.status is ErpPoStatus.REJECTED:
        ctx.notes.append(f"ERP rejected the order: {submitted.status_reason}")
        return ctx.result(ExecutionStatus.ESCALATED, submitted, deviations=tuple(devs))

    final = await erp.get(session, draft.erp_number)
    # Verify against the draft we accepted, so an already-noted ETA change is not reported twice.
    accepted = order.model_copy(
        update={
            "unit_price_inr": draft.unit_price_inr,
            "case_pack": draft.case_pack,
            "eta": draft.eta,
        }
    )
    after: list[Deviation] = compare(accepted, final, settings.erp)
    if after:
        ctx.notes.append(
            f"Submitted PO differs from the approval ({final.status_reason}); "
            "cancel or amend needs human approval"
        )
        return ctx.result(ExecutionStatus.NEEDS_HUMAN, final, deviations=tuple(after))
    return ctx.result(ExecutionStatus.COMPLETED, final, deviations=tuple(devs), flags=flags)
