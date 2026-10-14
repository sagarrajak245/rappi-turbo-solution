"""Draft/PO verification: which ERP differences matter and how much (KB D21)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.core.config import ErpSettings
from app.modules.erp_mock.schemas import ErpPurchaseOrderOut
from app.modules.execution.schemas import ApprovedOrder, Severity
from app.modules.execution.verify import compare
from app.shared.enums import ErpPoStatus

ETA = date(2026, 10, 17)
ORDER = ApprovedOrder(
    proposal_id="p1",
    node_code="N1",
    sku="SKU1",
    supplier_code="SUP1",
    qty=240,
    case_pack=24,
    unit_price_inr=Decimal("100.00"),
    eta=ETA,
)
NOW = datetime(2026, 10, 14, tzinfo=UTC)


def po(**changes: Any) -> ErpPurchaseOrderOut:
    base: dict[str, Any] = {
        "erp_number": "ERP-1",
        "idempotency_key": "p1:create",
        "node_code": "N1",
        "sku": "SKU1",
        "supplier_code": "SUP1",
        "qty": 240,
        "case_pack": 24,
        "unit_price_inr": Decimal("100.00"),
        "total_inr": Decimal("24000.00"),
        "eta": ETA,
        "status": ErpPoStatus.DRAFT,
        "mock_behaviour": None,
        "status_reason": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    return ErpPurchaseOrderOut(**{**base, **changes})


def fields(devs: list[Any]) -> dict[str, Severity]:
    return {d.field: d.severity for d in devs}


def test_identical_po_has_no_deviation() -> None:
    assert compare(ORDER, po(), ErpSettings()) == []


@pytest.mark.parametrize(
    ("price", "expected"),
    [("102.00", {}), ("102.01", {"unit_price_inr": Severity.MATERIAL}), ("108.00", {"unit_price_inr": Severity.MATERIAL})],
)  # fmt: skip
def test_price_within_tolerance_is_ignored(price: str, expected: dict[str, Severity]) -> None:
    assert fields(compare(ORDER, po(unit_price_inr=Decimal(price)), ErpSettings())) == expected


def test_case_pack_change_is_material() -> None:
    assert fields(compare(ORDER, po(case_pack=12), ErpSettings())) == {
        "case_pack": Severity.MATERIAL
    }


def test_eta_within_tolerance_is_ignored_later_is_minor() -> None:
    s = ErpSettings()
    assert compare(ORDER, po(eta=ETA + timedelta(days=1)), s) == []
    assert fields(compare(ORDER, po(eta=ETA + timedelta(days=3)), s)) == {"eta": Severity.MINOR}


def test_qty_or_supplier_mismatch_is_unfixable() -> None:
    devs = compare(ORDER, po(qty=200, supplier_code="OTHER"), ErpSettings())
    assert fields(devs) == {"qty": Severity.UNFIXABLE, "supplier_code": Severity.UNFIXABLE}
    qty = next(d for d in devs if d.field == "qty")
    assert (qty.expected, qty.actual) == ("240", "200")
