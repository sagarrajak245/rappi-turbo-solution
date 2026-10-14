"""Seeded ERP surprises (feedback-loop cases F1-F6), dispatched by name and stage.

A hook mutates the PO and the behaviour row in place and returns True when the caller must
simulate a timeout after committing (the PO exists but the client never saw the answer).
"""

from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal

from app.modules.erp_mock.models import ErpBehaviour, ErpPurchaseOrder
from app.shared.enums import ErpPoStatus
from app.shared.money import to_inr

Hook = Callable[[ErpPurchaseOrder, ErpBehaviour], bool]


def _fire(po: ErpPurchaseOrder, b: ErpBehaviour, reason: str) -> None:
    po.mock_behaviour = b.behaviour
    po.status_reason = reason
    b.times_fired += 1


def _price_change(po: ErpPurchaseOrder, b: ErpBehaviour) -> bool:
    pct = Decimal(str(b.params["pct"]))
    old = po.unit_price_inr
    po.unit_price_inr = to_inr(old * (1 + pct / 100))
    po.total_inr = to_inr(po.unit_price_inr * po.qty)
    _fire(po, b, f"Supplier price changed by {pct}%: {old} -> {po.unit_price_inr} per unit")
    return False


def _case_pack_change(po: ErpPurchaseOrder, b: ErpBehaviour) -> bool:
    old = po.case_pack
    po.case_pack = int(b.params["case_pack"])
    reason = f"Case pack changed from {old} to {po.case_pack}"
    if po.qty % po.case_pack:
        reason += f"; qty {po.qty} is not a multiple of the new case pack"
    _fire(po, b, reason)
    return False


def _late_eta(po: ErpPurchaseOrder, b: ErpBehaviour) -> bool:
    days = int(b.params["days"])
    po.eta = po.eta + timedelta(days=days)
    _fire(po, b, f"Supplier pushed the ETA back by {days} days")
    return False


def _timeout_after_create(po: ErpPurchaseOrder, b: ErpBehaviour) -> bool:
    if b.times_fired > 0:
        return False  # only the first create times out
    _fire(po, b, "ERP created the PO but the response timed out")
    return True


def _reject_on_submit(po: ErpPurchaseOrder, b: ErpBehaviour) -> bool:
    po.status = ErpPoStatus.REJECTED
    _fire(po, b, str(b.params["reason"]))
    return False


def _mismatch_after_submit(po: ErpPurchaseOrder, b: ErpBehaviour) -> bool:
    old = po.qty
    po.qty = int(b.params["qty"])
    po.total_inr = to_inr(po.unit_price_inr * po.qty)
    _fire(po, b, f"Supplier confirmed qty {po.qty} instead of the requested {old}")
    return False


BEHAVIOURS: dict[str, dict[str, Hook]] = {
    "price_change": {"create": _price_change},
    "case_pack_change": {"create": _case_pack_change},
    "late_eta": {"create": _late_eta},
    "timeout_after_create": {"create": _timeout_after_create},
    "reject_on_submit": {"submit": _reject_on_submit},
    "mismatch_after_submit": {"submit": _mismatch_after_submit},
}


def apply(stage: str, po: ErpPurchaseOrder, behaviour: ErpBehaviour | None) -> bool:
    """Run the behaviour's hook for this stage, if any. True means: time out after commit."""
    if behaviour is None:
        return False
    hook = BEHAVIOURS.get(behaviour.behaviour, {}).get(stage)
    return hook(po, behaviour) if hook else False
