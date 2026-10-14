"""Compare what we approved with what the ERP holds. Pure; tolerances come from config."""

from collections.abc import Callable
from datetime import timedelta

from app.core.config import ErpSettings
from app.modules.erp_mock.schemas import ErpPurchaseOrderOut
from app.modules.execution.schemas import ApprovedOrder, Deviation, Severity

Check = Callable[[ApprovedOrder, ErpPurchaseOrderOut, ErpSettings], bool]


def _price(o: ApprovedOrder, po: ErpPurchaseOrderOut, s: ErpSettings) -> bool:
    if o.unit_price_inr == 0:
        return po.unit_price_inr != 0
    change = abs(po.unit_price_inr - o.unit_price_inr) / o.unit_price_inr
    return round(float(change), 9) > s.price_tolerance_pct


def _late(o: ApprovedOrder, po: ErpPurchaseOrderOut, s: ErpSettings) -> bool:
    return po.eta > o.eta + timedelta(days=s.eta_tolerance_days)


def _differs(field: str) -> Check:
    return lambda o, po, _: getattr(o, field) != getattr(po, field)


# field -> (is it a deviation?, how bad is it). Order is the order deviations are reported in.
CHECKS: dict[str, tuple[Check, Severity]] = {
    "supplier_code": (_differs("supplier_code"), Severity.UNFIXABLE),
    "qty": (_differs("qty"), Severity.UNFIXABLE),
    "unit_price_inr": (_price, Severity.MATERIAL),
    "case_pack": (_differs("case_pack"), Severity.MATERIAL),
    "eta": (_late, Severity.MINOR),
}


def compare(order: ApprovedOrder, po: ErpPurchaseOrderOut, s: ErpSettings) -> list[Deviation]:
    return [
        Deviation(
            field=field,
            expected=str(getattr(order, field)),
            actual=str(getattr(po, field)),
            severity=severity,
        )
        for field, (check, severity) in CHECKS.items()
        if check(order, po, s)
    ]
