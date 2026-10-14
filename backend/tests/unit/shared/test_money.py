from decimal import Decimal

import pytest

from app.shared.money import format_inr, to_inr


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("125000"), "₹1,25,000"),
        (Decimal("1234567.5"), "₹12,34,567.50"),
        (Decimal("999"), "₹999"),
        (Decimal("150000.00"), "₹1,50,000"),
        (Decimal("-1000"), "-₹1,000"),
    ],
)
def test_format_inr_uses_indian_grouping(amount: Decimal, expected: str) -> None:
    assert format_inr(amount) == expected


def test_to_inr_quantizes_to_paise_half_up() -> None:
    assert to_inr("240") == Decimal("240.00")
    assert to_inr(0.125) == Decimal("0.13")
    assert to_inr(Decimal("240.00")) == to_inr(240)
